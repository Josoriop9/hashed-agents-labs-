"""
agent_core.py — MAFAgent Reusable Class
========================================

REFACTOR v2 — AsyncRunner Pattern (April 2026)
-----------------------------------------------
PROBLEM with v1 (nest_asyncio + shared event loop):
  After ~10 interactions, the shared event loop accumulated state:
  - Pending WAL flush tasks retrying failed backend calls
  - aiohttp connection pool exhaustion
  - asyncio.sleep() coroutines not GC'd
  Result: WAL flush fails silently → logs stop appearing in hashed logs list
  Workaround: F5 (creates new event loop) — NOT acceptable in production.

SOLUTION — Dedicated background thread with its own event loop (AsyncRunner):
  - All Hashed SDK operations run in a DEDICATED background thread
  - Main thread stays sync (no nest_asyncio needed)
  - asyncio.run_coroutine_threadsafe() correctly propagates exceptions
  - NO belt-and-suspenders needed for denied tools — exceptions work!
  - Event loop stays clean indefinitely (no state accumulation)
  - WAL flush runs in the dedicated loop, unaffected by main thread

DESIGN PATTERN: "Core / Shell"
  Core  → agent_core.py  (pure logic, no I/O)
  Shell → app.py, agent.py (UI layer, decides how to display)
"""

import asyncio
import base64
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

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
from azure.identity import DefaultAzureCredential

# ── Hashed SDK ────────────────────────────────────────────────────────────────
from hashed import HashedConfig, HashedCore, load_or_create_identity

# ── Local tools ───────────────────────────────────────────────────────────────
from tools import init_tools, TOOLS

load_dotenv()


# =============================================================================
# AsyncRunner — Dedicated background event loop
# =============================================================================

class AsyncRunner:
    """
    Runs all async SDK operations in a dedicated background thread.

    WHY THIS EXISTS:
      The Hashed SDK is fully async (aiohttp, asyncio tasks, WAL flush).
      Streamlit and Azure AI Agents dispatch are synchronous.

      The naive solution (nest_asyncio + shared loop) causes state
      accumulation: after ~10 interactions, pending WAL flush tasks and
      exhausted aiohttp connections make the shared loop "dirty".
      Logs stop appearing in hashed logs list. F5 "fixes" it because
      it creates a new event loop — but that's not acceptable.

      The correct solution: run ALL async operations in a DEDICATED
      background thread with its own event loop. The main thread stays
      synchronously clean. asyncio.run_coroutine_threadsafe() correctly
      propagates exceptions (unlike nest_asyncio + run_until_complete).

    USAGE:
      runner = AsyncRunner()
      result = runner.run(some_async_fn())   # blocks until done
      runner.stop()                           # on shutdown
    """

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_forever,
            daemon=True,
            name="hashed-async-runner",
        )
        self._thread.start()

    def _run_forever(self) -> None:
        """Entry point for background thread — runs event loop forever."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro, timeout: float = 30.0):
        """
        Submit a coroutine to the dedicated loop and block until result.

        Correctly propagates ALL exceptions (including PolicyViolationError)
        to the calling thread — no belt-and-suspenders needed.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def stop(self) -> None:
        """Stop the background event loop and thread."""
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


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
    message: str
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

    v2: Fully synchronous public API — no asyncio.run() needed from callers.
    Internally uses AsyncRunner for all Hashed SDK operations.

    Usage:
        agent = MAFAgent()
        agent.initialize()                      # ← sync now

        response = agent.chat("Compare MAF and LangChain")
        print(response.message)

        agent.shutdown()                        # ← sync now

    Thread safety: Not thread-safe. Use one instance per user session.
    For multi-user: create one MAFAgent per session (Streamlit session_state).
    """

    def __init__(self):
        self._runner: Optional[AsyncRunner] = None
        self.core: Optional[HashedCore] = None
        self.client: Optional[AgentsClient] = None
        self.agent_id: Optional[str] = None
        self.toolset: Optional[ToolSet] = None
        self.fn_registry: dict = {}
        self.policies: list[PolicyStatus] = []
        self.model = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
        self._initialized = False

    # ── 1. Initialization ─────────────────────────────────────────────────────

    def initialize(self) -> None:
        """
        Full synchronous initialization:
          1. Start dedicated async runner (background thread)
          2. Hashed identity + policies (run in dedicated loop)
          3. Azure AI Agents client (sync)
          4. Create persistent agent on Azure (sync)
        """
        self._runner = AsyncRunner()
        self._setup_hashed()
        self._configure_policies()
        self._setup_azure_client()
        self._build_toolset()
        self._create_azure_agent()
        self._initialized = True

    def _setup_hashed(self) -> None:
        """
        Load identity and initialize Hashed Core in the dedicated runner.

        PEM PERSISTENCE STRATEGY:
          The PEM file is the cryptographic identity of the agent.
          In containers, the filesystem is ephemeral — so we store it
          as a base64-encoded Azure Container Apps Secret (HASHED_PEM_B64),
          and write it to /tmp at startup.

          Priority:
            1. HASHED_PEM_B64 env var (Azure Secret, production)
            2. Local file ./secrets/maf_research_agent.pem (dev/local)
        """
        password = os.getenv("HASHED_IDENTITY_PASSWORD", "changeme")

        pem_b64 = os.getenv("HASHED_PEM_B64")
        if pem_b64:
            pem_path = "/tmp/maf_research_agent.pem"
            with open(pem_path, "wb") as f:
                f.write(base64.b64decode(pem_b64))
        else:
            pem_path = "./secrets/maf_research_agent.pem"

        identity = load_or_create_identity(pem_path, password)
        config = HashedConfig()
        self.core = HashedCore(
            config=config,
            identity=identity,
            agent_name="MAF Research Agent",
            agent_type="research",
        )
        # Run async initialize in the dedicated loop
        self._runner.run(self.core.initialize())

    def _configure_policies(self) -> None:
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
            self._runner.run(self.core.push_policies_to_backend())
        except Exception:
            pass  # Local policies still work

    def _setup_azure_client(self) -> None:
        """Create the Azure AI Agents client (synchronous)."""
        endpoint = os.getenv("AZURE_AI_AGENTS_ENDPOINT")
        if not endpoint:
            raise ValueError(
                "AZURE_AI_AGENTS_ENDPOINT not set in .env\n"
                "Get it from: ai.azure.com → Your Project → Overview"
            )
        self.client = AgentsClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
        )

    def _build_toolset(self) -> None:
        """
        Activate Hashed guards and build sync wrappers for Azure AI Agents.

        v2 SIMPLIFICATION vs v1:
          - No nest_asyncio
          - No loop.run_until_complete()
          - Uses self._runner.run() — dedicated background loop
          - asyncio.run_coroutine_threadsafe() correctly propagates exceptions
          - Denied tools use simple try/except (no belt-and-suspenders!)
          - No asyncio.sleep(0.2) WAL flush hack needed
        """
        if self.core is None:
            raise RuntimeError("Hashed core not initialized")

        # Activate @_guard decorators on all tools
        init_tools(self.core)

        # ── Tool wrappers — use runner for async Hashed calls ─────────────────

        def search_web(query: str) -> str:
            """
            Search for information on a topic.
            Use when the user asks about facts, documentation, or recent news.
            Args:
                query (str): The search query string
            Returns:
                str: Search results
            """
            result = self._runner.run(TOOLS["search_web"](query))
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
            result = self._runner.run(TOOLS["analyze_data"](topic, depth))
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
            result = self._runner.run(TOOLS["generate_report"](title, content_summary))
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
            result = self._runner.run(TOOLS["compare_frameworks"](framework_a, framework_b))
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
            # v2: simple try/except works correctly with AsyncRunner.
            # run_coroutine_threadsafe() propagates PolicyViolationError to this thread.
            # No belt-and-suspenders needed — the exception arrives reliably.
            try:
                self._runner.run(TOOLS["send_email"](to=to, subject=subject, body=body))
                return f"Email sent to {to}: {subject}"
            except Exception as e:
                return f"Action denied by security policy: send_email is not permitted ({e})"

        def delete_data(target: str) -> str:
            """
            Delete data, records, or files from the system.
            Use when asked to delete, remove, drop, or erase data.
            Args:
                target (str): The data, table, or resource to delete
            Returns:
                str: Result or denial message
            """
            try:
                self._runner.run(TOOLS["delete_data"](target=target))
                return f"Deleted: {target}"
            except Exception as e:
                return f"Action denied by security policy: delete_data is not permitted ({e})"

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
        """Create the agent on Azure Foundry."""
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
        Fully synchronous — no asyncio.run() needed from caller.

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
            thread = self.client.threads.create()
            self.client.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=message,
            )

            run = self.client.runs.create(
                thread_id=thread.id,
                agent_id=self.agent_id,
            )

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

    def shutdown(self, delete_agent: bool = False) -> None:
        """
        Clean up resources (synchronous in v2).

        Args:
            delete_agent: If True, delete the Azure agent.
        """
        if self.client and self.agent_id and delete_agent:
            try:
                self.client.delete_agent(self.agent_id)
            except Exception:
                pass

        if self.core and self._runner:
            try:
                self._runner.run(self.core.shutdown(), timeout=10)
            except Exception:
                pass

        if self._runner:
            self._runner.stop()
            self._runner = None

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
