"""
agent_core.py — MAFAgent Reusable Class
========================================

This module extracts the core agent logic from agent.py into a reusable
class that can be called from:
  - app.py (Streamlit UI)
  - agent.py (CLI script)
  - any other interface (API, tests, notebooks...)

DESIGN PATTERN: "Core / Shell"
  Core  → agent_core.py  (pure logic, no I/O)
  Shell → app.py, agent.py (UI layer, decides how to display)

WHAT THIS CLASS DOES:
  1. Initializes Hashed SDK (identity + policies)
  2. Connects to Azure AI Agents
  3. Creates and persists the Azure AI Agent (reused across conversations)
  4. Exposes a chat(message) method that:
       a. Sends the message to the agent
       b. Polls the run loop
       c. Dispatches tool calls through Hashed guards
       d. Returns structured response with metadata
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import nest_asyncio
from dotenv import load_dotenv

# ── Azure AI Agents SDK ───────────────────────────────────────────────────────
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    FunctionTool,
    MessageRole,
    RunStatus,
    ToolOutput,
    ToolSet,
)
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

# ── Hashed SDK ────────────────────────────────────────────────────────────────
from hashed import HashedConfig, HashedCore, load_or_create_identity

# ── Local tools ───────────────────────────────────────────────────────────────
from tools import init_tools, TOOLS

load_dotenv()
nest_asyncio.apply()


# =============================================================================
# Data Classes — Structured responses
# =============================================================================

@dataclass
class ToolCallRecord:
    """Represents a single tool call made during a run."""
    name: str
    arguments: dict
    output: str
    allowed: bool = True
    error: Optional[str] = None


@dataclass
class ChatResponse:
    """Structured response from a single chat turn."""
    message: str                             # The agent's text response
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    run_id: Optional[str] = None
    agent_id: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class PolicyStatus:
    """Summary of active policies for display in the UI."""
    name: str
    allowed: bool


# =============================================================================
# MAFAgent — The reusable core class
# =============================================================================

class MAFAgent:
    """
    Reusable MAF Research Agent.

    Usage:
        agent = MAFAgent()
        asyncio.run(agent.initialize())

        response = agent.chat("Compare MAF and LangChain")
        print(response.message)
        for tc in response.tool_calls:
            print(f"  Used: {tc.name}")

        asyncio.run(agent.shutdown())

    Thread safety: Not thread-safe. Use one instance per user session.
    For multi-user: create one MAFAgent per session (Streamlit session_state).
    """

    def __init__(self):
        self.core: Optional[HashedCore] = None
        self.client: Optional[AgentsClient] = None
        self.agent_id: Optional[str] = None
        self.toolset: Optional[ToolSet] = None
        self.fn_registry: dict = {}
        self.policies: list[PolicyStatus] = []
        self.model = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
        self._initialized = False

    # ── 1. Initialization ─────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """
        Full initialization:
          1. Hashed identity + policies
          2. Azure AI Agents client
          3. Create persistent agent on Azure
        """
        await self._setup_hashed()
        await self._configure_policies()
        self._setup_azure_client()
        self._build_toolset()
        self._create_azure_agent()
        self._initialized = True

    async def _setup_hashed(self) -> None:
        """
        Load identity and initialize Hashed Core.

        PEM PERSISTENCE STRATEGY:
          The PEM file is the cryptographic identity of the agent.
          In containers, the filesystem is ephemeral — so we store it
          as a base64-encoded Azure Container Apps Secret (HASHED_PEM_B64),
          and write it to /tmp at startup.

          Priority:
            1. HASHED_PEM_B64 env var (Azure Secret, production)
            2. Local file ./secrets/maf_research_agent.pem (dev/local)
        """
        import base64

        password = os.getenv("HASHED_IDENTITY_PASSWORD", "changeme")

        pem_b64 = os.getenv("HASHED_PEM_B64")
        if pem_b64:
            # Production: write PEM from Azure Secret to /tmp
            pem_path = "/tmp/maf_research_agent.pem"
            with open(pem_path, "wb") as f:
                f.write(base64.b64decode(pem_b64))
        else:
            # Development: use local file (will create if missing)
            pem_path = "./secrets/maf_research_agent.pem"

        identity = load_or_create_identity(pem_path, password)
        config = HashedConfig()
        self.core = HashedCore(
            config=config,
            identity=identity,
            agent_name="MAF Research Agent",
            agent_type="research",
        )
        await self.core.initialize()

    async def _configure_policies(self) -> None:
        """Add policies to the Hashed policy engine."""
        policy_config = [
            ("search_web",         True,  {"max_per_hour": 20,  "risk": "low"}),
            ("analyze_data",       True,  {"max_per_hour": 50,  "risk": "low"}),
            ("generate_report",    True,  {"max_per_hour": 10,  "risk": "low"}),
            ("compare_frameworks", True,  {"max_per_hour": 30,  "risk": "low"}),
            ("delete_data",        False, {"risk": "critical"}),
            ("send_email",         False, {"risk": "high", "reason": "requires_human_approval"}),
        ]

        for name, allowed, meta in policy_config:
            self.core.policy_engine.add_policy(name, allowed=allowed, metadata=meta)
            self.policies.append(PolicyStatus(name=name, allowed=allowed))

        # Sync with backend — non-fatal if it fails
        try:
            await self.core.push_policies_to_backend()
        except Exception:
            pass  # Local policies still work

    def _setup_azure_client(self) -> None:
        """
        Create the Azure AI Agents client.

        Auth strategy:
          - In Container Apps: uses System-assigned Managed Identity automatically
            (DefaultAzureCredential picks up the MI token from the IMDS endpoint)
          - Locally: uses 'az login' credentials via AzureCliCredential
          - DefaultAzureCredential tries both in order — no config needed

        To enable Managed Identity, run once:
          az containerapp identity assign --name maf-research-agent \
              --resource-group <your-resource-group> --system-assigned

        Then assign the role:
          az role assignment create \
              --assignee <principalId> \
              --role "Cognitive Services User" \
              --scope /subscriptions/.../resourceGroups/<your-resource-group>
        """
        endpoint = os.getenv("AZURE_AI_AGENTS_ENDPOINT")
        if not endpoint:
            raise ValueError(
                "AZURE_AI_AGENTS_ENDPOINT not set in .env\n"
                "Get it from: ai.azure.com → Your Project → Overview"
            )

        # DefaultAzureCredential automatically uses:
        #   1. Managed Identity (when running in Container Apps with MI enabled)
        #   2. AzureCliCredential (when running locally with az login)
        #   3. Environment variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
        credential = DefaultAzureCredential()

        self.client = AgentsClient(
            endpoint=endpoint,
            credential=credential,
        )

    def _build_toolset(self) -> None:
        """
        Activate Hashed guards and wrap async tools into sync functions
        for the Azure AI Agents FunctionTool.

        PATTERN (same as Hashed template):
          tools.init_tools(core)    ← activates @_guard decorators
          from tools import TOOLS   ← module-level guarded functions

        Then we create sync wrappers because Azure SDK dispatches
        tool calls synchronously — bridged via asyncio event loop.
        """
        if self.core is None:
            raise RuntimeError("Hashed core not initialized")

        # ── Activate @_guard decorators (equivalent to @core.guard()) ─────────
        init_tools(self.core)
        loop = asyncio.get_event_loop()

        # ── Sync wrappers — Azure SDK needs synchronous callables ─────────────
        # Each wrapper calls the async @_guard-decorated function via event loop.
        # The Hashed guard runs inside the async function before executing.
        #
        # NOTE on denial WAL flush:
        #   For denied tools, we use TWO separate loop.run_until_complete() calls:
        #   1st: the guarded tool call (raises exception on denial)
        #   2nd: asyncio.sleep() to pump the event loop and flush WAL to backend
        #
        #   We do NOT use asyncio.sleep() inside the except block of an async
        #   function, because nest_asyncio + raise-after-await can swallow
        #   the exception, causing the denial to appear as a success.

        def search_web(query: str) -> str:
            """
            Search for information on a topic.
            Use when the user asks about facts, documentation, or recent news.
            Args:
                query (str): The search query string
            Returns:
                str: Search results
            """
            result = loop.run_until_complete(TOOLS["search_web"](query))
            lines = "\n".join(f"• {r}" for r in result["results"])
            return f"Search results for '{query}':\n{lines}"

        def analyze_data(topic: str, depth: str = "medium") -> str:
            """
            Analyze a topic — pros, cons, trends, use cases.
            Args:
                topic (str): Topic to analyze (e.g. 'azure', 'maf', 'langchain')
                depth (str): 'quick', 'medium', or 'deep'. Default: medium
            Returns:
                str: Structured analysis
            """
            result = loop.run_until_complete(TOOLS["analyze_data"](topic, depth))
            a = result["analysis"]
            return (
                f"Analysis of '{topic}':\n"
                f"  ✅ Pros: {', '.join(a['pros'])}\n"
                f"  ❌ Cons: {', '.join(a['cons'])}\n"
                f"  📈 Trend: {a['trend']}\n"
                f"  🎯 Use cases: {', '.join(a['use_cases'])}"
            )

        def generate_report(title: str, content_summary: str) -> str:
            """
            Generate a professional Markdown report.
            Args:
                title (str): Report title
                content_summary (str): Summary of findings
            Returns:
                str: Complete Markdown report
            """
            result = loop.run_until_complete(TOOLS["generate_report"](title, content_summary))
            return result["report_markdown"]

        def compare_frameworks(framework_a: str, framework_b: str) -> str:
            """
            Compare two AI agent frameworks side by side.
            Use when asked to compare MAF, LangChain, CrewAI, AutoGen, Strands, etc.
            Args:
                framework_a (str): First framework (e.g. 'maf', 'langchain', 'crewai')
                framework_b (str): Second framework (e.g. 'autogen', 'strands')
            Returns:
                str: Comparison with scores and verdict
            """
            result = loop.run_until_complete(TOOLS["compare_frameworks"](framework_a, framework_b))
            return (
                f"Framework comparison: {framework_a} vs {framework_b}\n"
                f"  Score {framework_a}: {result['scores'][framework_a]}/{result['max_score']}\n"
                f"  Score {framework_b}: {result['scores'][framework_b]}/{result['max_score']}\n"
                f"  Winner: {result['winner']}\n"
                f"  Verdict: {result['verdict']}"
            )

        def send_email(to: str, subject: str, body: str) -> str:
            """
            Send an email to a recipient.
            Use when asked to send, email, notify, or contact someone.
            Args:
                to (str): Recipient email address
                subject (str): Email subject line
                body (str): Email message body
            Returns:
                str: Result or denial message
            """
            # 1. Call guarded tool → this LOGS the attempt to Hashed backend
            #    Note: with nest_asyncio, PolicyViolationError may not propagate
            #    correctly from run_until_complete — we handle this in step 3.
            try:
                loop.run_until_complete(TOOLS["send_email"](to=to, subject=subject, body=body))
            except Exception:
                pass  # Exception may or may not propagate — handled below

            # 2. Pump event loop → gives Hashed WAL time to flush denial to backend
            try:
                loop.run_until_complete(asyncio.sleep(0.2))
            except Exception:
                pass

            # 3. Belt-and-suspenders: check LOCAL policy config
            #    This catches the case where nest_asyncio swallows the exception
            #    but the guard has already logged the denial to the backend.
            policy = next((p for p in self.policies if p.name == "send_email"), None)
            if policy and not policy.allowed:
                return "Action denied by security policy: send_email is not permitted (policy: denied)"

            return f"Email sent to {to}: {subject}"

        def delete_data(target: str) -> str:
            """
            Delete data, records, or files from the system.
            Use when asked to delete, remove, drop, or erase data.
            Args:
                target (str): The data, table, or resource to delete
            Returns:
                str: Result or denial message
            """
            # 1. Call guarded tool → logs to Hashed backend
            try:
                loop.run_until_complete(TOOLS["delete_data"](target=target))
            except Exception:
                pass

            # 2. WAL flush
            try:
                loop.run_until_complete(asyncio.sleep(0.2))
            except Exception:
                pass

            # 3. Local policy check (belt-and-suspenders)
            policy = next((p for p in self.policies if p.name == "delete_data"), None)
            if policy and not policy.allowed:
                return "Action denied by security policy: delete_data is not permitted (policy: denied)"

            return f"Deleted: {target}"

        function_tool = FunctionTool(
            functions={search_web, analyze_data, generate_report, compare_frameworks, send_email, delete_data}
        )
        self.toolset = ToolSet()
        self.toolset.add(function_tool)

        # Build name→callable registry for manual dispatch
        for tool in self.toolset._tools:
            if isinstance(tool, FunctionTool):
                self.fn_registry.update(tool._functions)

    def _create_azure_agent(self) -> None:
        """
        Create the agent on Azure Foundry.
        In production: reuse if already created (store agent_id in DB or env).
        """
        azure_agent = self.client.create_agent(
            model=self.model,
            name="MAF-Research-Agent",
            instructions="""You are a professional AI research assistant specializing in AI agent frameworks.

## Available tools:
- search_web: Search for information on any topic
- analyze_data: Deep analysis of technologies with pros/cons/trends
- generate_report: Create professional Markdown reports
- compare_frameworks: Side-by-side framework comparison with scores
- send_email: Send an email to a recipient
- delete_data: Delete data, records, or files from the system

## IMPORTANT — Security enforcement:
ALL tool calls go through the Hashed security policy engine AUTOMATICALLY.
- You do NOT need to pre-screen or refuse tool calls.
- ALWAYS attempt to use the tool when the user requests it.
- If a tool is blocked by policy, the security system will deny it and you will receive:
  "Action denied by security policy: ..."
- When you receive a denial, inform the user: "That action was blocked by the security policy."

## Guidelines:
- Always use tools to provide accurate, up-to-date information.
- When comparing frameworks, always use compare_frameworks tool.
- Respond in the same language as the user.
- Mention which tool you used for transparency.

Security: All operations are cryptographically monitored and enforced by Hashed SDK at the infrastructure level — not at the prompt level.
""",
            toolset=self.toolset,
        )
        self.agent_id = azure_agent.id

    # ── 2. Chat ────────────────────────────────────────────────────────────────

    def chat(self, message: str) -> ChatResponse:
        """
        Send a message and get a structured response.

        This is the main method to call from any interface.
        It handles the full Azure AI Agents run loop with tool dispatch.

        Args:
            message: The user's message

        Returns:
            ChatResponse with message, tool_calls, and metadata
        """
        if not self._initialized:
            return ChatResponse(
                message="Agent not initialized. Call initialize() first.",
                error="Not initialized",
            )

        tool_calls_made: list[ToolCallRecord] = []

        try:
            # Create thread + message
            thread = self.client.threads.create()
            self.client.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=message,
            )

            # Start run
            run = self.client.runs.create(
                thread_id=thread.id,
                agent_id=self.agent_id,
            )

            # Poll loop
            poll_interval = 1.0
            max_wait = 120
            elapsed = 0

            while run.status in (RunStatus.QUEUED, RunStatus.IN_PROGRESS, RunStatus.REQUIRES_ACTION):
                if elapsed >= max_wait:
                    return ChatResponse(
                        message="Request timed out.",
                        error=f"Timeout after {max_wait}s",
                        run_id=run.id,
                        agent_id=self.agent_id,
                        model=self.model,
                    )

                if run.status == RunStatus.REQUIRES_ACTION:
                    tool_outputs = []

                    for tc in run.required_action.submit_tool_outputs.tool_calls:
                        fn_name = tc.function.name
                        fn_args = json.loads(tc.function.arguments or "{}")
                        record = ToolCallRecord(name=fn_name, arguments=fn_args, output="")

                        if fn_name in self.fn_registry:
                            try:
                                output = self.fn_registry[fn_name](**fn_args)
                                record.output = str(output)
                                # Denied tools return a string starting with "Action denied"
                                # (they catch the exception internally to return gracefully)
                                if str(output).startswith("Action denied by security policy"):
                                    record.allowed = False
                                    record.error = str(output)
                                else:
                                    record.allowed = True
                            except Exception as e:
                                err_msg = str(e)
                                record.output = f"Error: {err_msg}"
                                record.error = err_msg
                                record.allowed = False
                        else:
                            record.output = f"Function '{fn_name}' not found."
                            record.error = "Function not found"

                        tool_calls_made.append(record)
                        tool_outputs.append(
                            ToolOutput(tool_call_id=tc.id, output=record.output)
                        )

                    run = self.client.runs.submit_tool_outputs(
                        thread_id=thread.id,
                        run_id=run.id,
                        tool_outputs=tool_outputs,
                    )
                else:
                    time.sleep(poll_interval)
                    elapsed += poll_interval
                    run = self.client.runs.get(thread_id=thread.id, run_id=run.id)

            # Check failure
            if run.status == RunStatus.FAILED:
                error_msg = str(getattr(run, "last_error", "Unknown error"))
                return ChatResponse(
                    message=f"Run failed: {error_msg}",
                    error=error_msg,
                    tool_calls=tool_calls_made,
                    run_id=run.id,
                    agent_id=self.agent_id,
                    model=self.model,
                )

            # Extract response
            messages = self.client.messages.list(thread_id=thread.id, order="desc")
            for msg in messages:
                if msg.role == MessageRole.AGENT:
                    for block in msg.content:
                        if hasattr(block, "text"):
                            return ChatResponse(
                                message=block.text.value,
                                tool_calls=tool_calls_made,
                                run_id=run.id,
                                agent_id=self.agent_id,
                                model=self.model,
                            )
                    break

            return ChatResponse(
                message="(No response from agent)",
                tool_calls=tool_calls_made,
                agent_id=self.agent_id,
                model=self.model,
            )

        except Exception as e:
            return ChatResponse(
                message=f"Error: {e}",
                error=str(e),
                tool_calls=tool_calls_made,
            )

    # ── 3. Shutdown ────────────────────────────────────────────────────────────

    async def shutdown(self, delete_agent: bool = False) -> None:
        """
        Clean up resources.

        Args:
            delete_agent: If True, delete the Azure agent (use for cleanup only).
                          In production, keep agents alive to avoid re-creation cost.
        """
        if self.client and self.agent_id and delete_agent:
            try:
                self.client.delete_agent(self.agent_id)
            except Exception:
                pass

        if self.core:
            await self.core.shutdown()

        self._initialized = False

    # ── 4. Properties ──────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._initialized

    @property
    def identity_hex(self) -> str:
        if self.core and hasattr(self.core, "identity"):
            return self.core.identity.public_key_hex[:32] + "..."
        return "unknown"

    @property
    def allowed_tools(self) -> list[str]:
        return [p.name for p in self.policies if p.allowed]

    @property
    def denied_tools(self) -> list[str]:
        return [p.name for p in self.policies if not p.allowed]
