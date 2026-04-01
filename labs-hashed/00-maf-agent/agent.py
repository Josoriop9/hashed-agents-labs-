"""
agent.py — MAF Research Agent | Azure AI Agents + Hashed SDK
=============================================================

STACK:
  • Azure AI Agents SDK  — Orchestration via Azure Foundry Agent Service
  • Hashed SDK           — Security: policies, identities, audit logs
  • Azure OpenAI GPT-4o  — Language model (reasoning + tool selection)
  • Docker / Foundry     — Production deployment (see Dockerfile + deploy/)

ARCHITECTURE:
  User / App
      │
      ▼
  AgentsClient (azure-ai-agents)
      │  creates agent, thread, run
      ▼
  Azure OpenAI GPT-4o
      │  decides which tool to call
      ▼
  FunctionTool → ToolSet
      │  dispatches to Python functions
      ▼
  Hashed @core.guard("tool_name")
      │  checks policy before execution
      ├── ✅ allowed → executes + logs
      └── ❌ denied  → PolicyViolationError
      │
      ▼
  Tool function (tools.py)

HOW TO RUN:
  python agent.py                         # interactive mode
  python agent.py --demo                  # automated demo
  python agent.py --query "your question" # single query

HOW TO DEPLOY TO AZURE FOUNDRY:
  see deploy/deploy.sh

WHAT YOU LEARN:
  1. How Azure AI Agents SDK works (threads, runs, tool calls)
  2. How to integrate Hashed SDK with any framework
  3. How to deploy an agent to Azure Foundry Agent Service
  4. Production-grade security patterns
"""

import asyncio
import argparse
import json
import os
import time
from dotenv import load_dotenv

# ── Azure AI Agents SDK ───────────────────────────────────────────────────────
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    FunctionTool,
    ToolSet,
    MessageRole,
    RunStatus,
)
from azure.identity import DefaultAzureCredential, AzureCliCredential

# ── Hashed SDK ────────────────────────────────────────────────────────────────
from hashed import HashedCore, HashedConfig, load_or_create_identity

# ── Local tools ───────────────────────────────────────────────────────────────
from tools import init_tools, TOOLS

load_dotenv()


# =============================================================================
# 1. HASHED SDK — Identity + Policies
# =============================================================================

async def setup_hashed() -> HashedCore:
    """
    Initialize Hashed SDK:
      - Load (or create) the agent's cryptographic identity
      - Register the agent on the Hashed backend
      - Sync policies from dashboard → local cache

    KEY CONCEPT:
      Every agent gets a unique identity backed by elliptic curve cryptography.
      The PEM file stores the private key.  The public key IS the agent's
      identifier in Hashed — think of it as a cryptographic username.
    """
    print("🔐 Initializing Hashed SDK...")

    password = os.getenv("HASHED_IDENTITY_PASSWORD", "changeme")
    identity = load_or_create_identity(
        "./secrets/maf_research_agent.pem",
        password
    )
    print(f"   Identity  : {identity.public_key_hex[:32]}...")

    config = HashedConfig()
    core = HashedCore(
        config=config,
        identity=identity,
        agent_name="MAF Research Agent",
        agent_type="research",
    )

    await core.initialize()
    print("   Hashed Core: ✅ initialized\n")
    return core


async def configure_policies(core: HashedCore) -> None:
    """
    Define security policies for each tool.

    KEY CONCEPT:
      Policies are the "rules of engagement" for the agent.
      - allowed=True  → operation can run (subject to limits)
      - allowed=False → PolicyViolationError raised before the function runs
      - metadata      → optional limits: max_per_hour, risk level, etc.

    Policies are stored in Hashed backend and cached locally,
    so they work even when the backend is temporarily unreachable.
    """
    print("📋 Configuring policies...")

    policy_config = {
        # Allowed operations
        "search_web":         {"allowed": True,  "meta": {"max_per_hour": 20,  "risk": "low"}},
        "analyze_data":       {"allowed": True,  "meta": {"max_per_hour": 50,  "risk": "low"}},
        "generate_report":    {"allowed": True,  "meta": {"max_per_hour": 10,  "risk": "low"}},
        "compare_frameworks": {"allowed": True,  "meta": {"max_per_hour": 30,  "risk": "low"}},
        # Blocked operations — demonstrate policy denial
        "delete_data":        {"allowed": False, "meta": {"risk": "critical"}},
        "send_email":         {"allowed": False, "meta": {"risk": "high", "reason": "requires_human_approval"}},
    }

    for name, cfg in policy_config.items():
        core.policy_engine.add_policy(
            name,
            allowed=cfg["allowed"],
            metadata=cfg.get("meta", {})
        )
        status = "✅ ALLOWED" if cfg["allowed"] else "🚫 DENIED "
        print(f"   {status}  {name}")

    # Push to Hashed dashboard (makes policies visible in the UI)
    # NOTE: This may fail if the agent identity is not yet registered
    # in a Hashed application. Local policies still work perfectly.
    try:
        await core.push_policies_to_backend()
        print("\n   Policies synced to Hashed dashboard ✅\n")
    except Exception as e:
        print(f"\n   ⚠️  Dashboard sync skipped ({e})")
        print("   Local policies are active — all guards will work.\n")


# =============================================================================
# 2. AZURE AI AGENTS — Build the Agent
# =============================================================================

def build_client() -> AgentsClient:
    """
    Create the Azure AI Agents client.

    WHAT IS AgentsClient?
      The central object that talks to Azure Foundry Agent Service.
      It manages agents (create/delete), threads (conversations),
      runs (execution sessions), and tool calls.

    AUTH OPTIONS (in order of recommendation):
      • DefaultAzureCredential → tries az login, env vars, managed identity
      • AzureCliCredential     → explicit az login (dev machines)
      • Managed Identity       → production on Azure VMs / containers

    NOTE: Azure AI Agents uses OAuth2 tokens (not API keys directly).
    Run `az login` before executing this script.
    """
    endpoint = os.getenv("AZURE_AI_AGENTS_ENDPOINT")

    if not endpoint:
        raise ValueError(
            "AZURE_AI_AGENTS_ENDPOINT not set.\n"
            "Format: https://<project>.services.ai.azure.com/api/projects/<project-name>\n"
            "Find it in ai.azure.com → Your Project → Overview"
        )

    # DefaultAzureCredential tries multiple auth methods automatically:
    # 1. az login (AzureCliCredential)
    # 2. Environment variables (AZURE_CLIENT_ID etc.)
    # 3. Managed Identity (when running on Azure)
    credential = DefaultAzureCredential()

    return AgentsClient(endpoint=endpoint, credential=credential)


def build_toolset(tools_dict: dict) -> tuple:
    """
    Wrap Hashed-protected functions into an Azure AI Agents ToolSet.

    HOW FUNCTION TOOLS WORK:
      1. FunctionTool(functions={...}) generates JSON schemas from docstrings
      2. The LLM sees those schemas and decides which function to call
      3. When called, Azure SDK dispatches to your Python function
      4. Your function runs through @core.guard() → Hashed policy check
      5. Result is returned to the LLM to formulate final response

    IMPORTANT: Function docstrings become the LLM's instructions.
    Write them clearly — the LLM uses them to decide WHEN and HOW to call each tool.
    """

    # Sync wrappers — Azure SDK dispatches functions synchronously
    # but our Hashed-protected functions are async.
    # We bridge them with asyncio.get_event_loop().run_until_complete()
    import nest_asyncio
    nest_asyncio.apply()

    def search_web(query: str) -> str:
        """
        Search for information on a topic (web search).
        Use when the user asks about facts, documentation, or recent news.
        Args:
            query (str): The search query string
        Returns:
            str: Search results formatted as a list
        """
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(tools_dict["search_web"](query))
        lines = "\n".join(f"• {r}" for r in result["results"])
        return f"Search results for '{query}':\n{lines}"

    def analyze_data(topic: str, depth: str = "medium") -> str:
        """
        Analyze a topic and provide structured pros/cons, trends, and use cases.
        Use when the user asks to evaluate or analyze a technology or concept.
        Args:
            topic (str): Topic to analyze (e.g. 'azure', 'maf', 'langchain')
            depth (str): Analysis depth — 'quick', 'medium', or 'deep'. Default: medium
        Returns:
            str: Structured analysis with pros, cons, trend, and use cases
        """
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(tools_dict["analyze_data"](topic, depth))
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
        Generate a professional research report in Markdown format.
        Use when the user asks to write a report, summary, or document.
        Args:
            title (str): The report title
            content_summary (str): Summary of findings to include in the report
        Returns:
            str: Complete report in Markdown format
        """
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(tools_dict["generate_report"](title, content_summary))
        return result["report_markdown"]

    def compare_frameworks(framework_a: str, framework_b: str) -> str:
        """
        Compare two AI agent frameworks side by side with scores.
        Use when asked to compare MAF, LangChain, CrewAI, AutoGen, Strands, etc.
        Args:
            framework_a (str): First framework (e.g. 'maf', 'langchain', 'crewai')
            framework_b (str): Second framework (e.g. 'autogen', 'strands')
        Returns:
            str: Comparison results with scores and verdict
        """
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(tools_dict["compare_frameworks"](framework_a, framework_b))
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
        loop = asyncio.get_event_loop()
        try:
            result = loop.run_until_complete(tools_dict["send_email"](to, subject, body))
            return f"Email sent to {to}: {subject}"
        except Exception as e:
            return f"Action denied by policy: {e}"

    def delete_data(target: str) -> str:
        """
        Delete data, records, or files from the system.
        Use when asked to delete, remove, drop, or erase data.
        Args:
            target (str): The data, table, or resource to delete
        Returns:
            str: Result or denial message
        """
        loop = asyncio.get_event_loop()
        try:
            result = loop.run_until_complete(tools_dict["delete_data"](target))
            return f"Deleted: {target}"
        except Exception as e:
            return f"Action denied by policy: {e}"

    # Build the ToolSet
    function_tool = FunctionTool(functions={search_web, analyze_data, generate_report, compare_frameworks, send_email, delete_data})
    toolset = ToolSet()
    toolset.add(function_tool)

    return toolset, function_tool


# =============================================================================
# 3. CONVERSATION ENGINE
# =============================================================================

def run_agent_query(client: AgentsClient, agent_id: str, toolset, message: str) -> str:
    """
    Execute a single query through the Azure AI Agents run loop.

    HOW A RUN WORKS (manual polling — works with any model):
      1. Create a Thread          → a conversation session
      2. Add a Message            → user's input
      3. Create a Run             → starts LLM processing
      4. Poll loop:
           • QUEUED / IN_PROGRESS → wait and poll again
           • REQUIRES_ACTION      → LLM wants to call a tool:
               a. Parse tool name + arguments from run.required_action
               b. Execute local Python function (goes through Hashed guard)
               c. Submit ToolOutput back to the run
               d. LLM receives result and continues
           • COMPLETED            → read final message
           • FAILED               → raise error

    KEY CONCEPT — Why manual instead of create_and_process?
      create_and_process() uses an internal function registry that can
      fail to find locally-defined functions.  The manual loop below
      dispatches tool calls directly from a plain dict {name: callable},
      which is simpler, debuggable, and works with any model (GPT-4o,
      DeepSeek, Llama, etc.).
    """
    from azure.ai.agents.models import ToolOutput

    # Build a plain name→function registry from the toolset
    # FunctionTool._functions is a dict {function_name: callable}
    fn_registry: dict = {}
    for tool in toolset._tools:
        if isinstance(tool, FunctionTool):
            fn_registry.update(tool._functions)

    print(f"  🗂️  Tool registry: {list(fn_registry.keys())}")

    # Step 1: Fresh thread for this conversation turn
    thread = client.threads.create()

    # Step 2: Add user message
    client.messages.create(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=message,
    )

    # Step 3: Start the run (do NOT pass toolset here — we handle dispatch manually)
    run = client.runs.create(
        thread_id=thread.id,
        agent_id=agent_id,
    )

    # Step 4: Poll loop
    poll_interval = 1.0  # seconds between polls
    max_wait      = 120  # seconds before timeout
    elapsed       = 0

    while run.status in (RunStatus.QUEUED, RunStatus.IN_PROGRESS, RunStatus.REQUIRES_ACTION):
        if elapsed >= max_wait:
            raise TimeoutError(f"Run timed out after {max_wait}s (status={run.status})")

        if run.status == RunStatus.REQUIRES_ACTION:
            # ── TOOL CALL DISPATCH ─────────────────────────────────────
            # This is the critical moment: the LLM decided to call a tool.
            # We execute the function locally (through Hashed guard) and
            # submit the result back so the LLM can continue.
            tool_outputs = []

            for tc in run.required_action.submit_tool_outputs.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments or "{}")

                print(f"  🔧 Tool call: {fn_name}({fn_args})")

                if fn_name in fn_registry:
                    try:
                        output = fn_registry[fn_name](**fn_args)
                        print(f"  ✅ {fn_name} → {str(output)[:80]}...")
                    except Exception as e:
                        output = f"Error in {fn_name}: {e}"
                        print(f"  ❌ {fn_name} error: {e}")
                else:
                    output = f"Function '{fn_name}' not found in registry."
                    print(f"  ⚠️  Unknown function: {fn_name}")

                tool_outputs.append(
                    ToolOutput(tool_call_id=tc.id, output=str(output))
                )

            # Submit results back to the run
            run = client.runs.submit_tool_outputs(
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=tool_outputs,
            )
        else:
            # QUEUED or IN_PROGRESS — just wait
            time.sleep(poll_interval)
            elapsed += poll_interval
            run = client.runs.get(thread_id=thread.id, run_id=run.id)

    # Step 5: Check final status
    if run.status == RunStatus.FAILED:
        error_msg = getattr(run, "last_error", "Unknown error")
        raise RuntimeError(f"Run failed: {error_msg}")

    # Step 6: Extract last assistant message
    messages = client.messages.list(thread_id=thread.id, order="desc")
    for msg in messages:
        if msg.role == MessageRole.AGENT:
            for block in msg.content:
                if hasattr(block, "text"):
                    return block.text.value
            break

    return "(No response from agent)"


# =============================================================================
# 4. MODES — Interactive / Demo / Single Query
# =============================================================================

def run_interactive(client: AgentsClient, agent_id: str, toolset) -> None:
    """Interactive chat loop."""
    print("\n" + "=" * 60)
    print("💬 MAF RESEARCH AGENT — Interactive Mode")
    print("=" * 60)
    print("\nTry these commands:")
    print("  • 'Search for information about MAF'")
    print("  • 'Analyze Azure AI Foundry'")
    print("  • 'Compare MAF and LangChain'")
    print("  • 'Generate a report about AI agents in 2026'")
    print("\nType 'exit' to quit\n")
    print("-" * 60)

    while True:
        try:
            user_input = input("\n👤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("\n👋 Goodbye!")
            break

        try:
            print()
            response = run_agent_query(client, agent_id, toolset, user_input)
            print(f"\n🤖 Agent:\n{response}")
            print("\n" + "-" * 60)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            if "endpoint" in str(e).lower() or "credential" in str(e).lower():
                print("   💡 Hint: Check AZURE_AI_AGENTS_ENDPOINT in your .env")


def run_demo(client: AgentsClient, agent_id: str, toolset) -> None:
    """Automated demo with predefined queries."""
    print("\n" + "=" * 60)
    print("🎯 MAF RESEARCH AGENT — Demo Mode")
    print("=" * 60)

    demo_queries = [
        "Search for information about Microsoft Agent Framework",
        "Analyze Azure AI Foundry as a platform for AI agents",
        "Compare MAF and LangChain — which one should I choose?",
        "Generate a report titled 'AI Agent Frameworks 2026'",
    ]

    for i, query in enumerate(demo_queries, 1):
        print(f"\n{'=' * 60}")
        print(f"DEMO STEP {i}/{len(demo_queries)}: {query}")
        print("=" * 60)
        try:
            response = run_agent_query(client, agent_id, toolset, query)
            print(f"\n🤖 Response:\n{response}\n")
            if i < len(demo_queries):
                input("▶  Press Enter for the next step...")
        except Exception as e:
            print(f"❌ Error: {e}")


def run_single_query(client: AgentsClient, agent_id: str, toolset, query: str) -> None:
    """Run a single query and print the result."""
    print(f"\n👤 Query: {query}\n")
    response = run_agent_query(client, agent_id, toolset, query)
    print(f"🤖 Response:\n{response}\n")


# =============================================================================
# 5. MAIN
# =============================================================================

async def main() -> None:
    parser = argparse.ArgumentParser(description="MAF Research Agent — Azure AI Agents + Hashed SDK")
    parser.add_argument("--demo",  action="store_true", help="Run automated demo")
    parser.add_argument("--query", type=str,            help="Run a single query and exit")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("🚀 MAF Research Agent")
    print("   Azure AI Agents SDK + Hashed SDK")
    print("   Azure Foundry Agent Service")
    print("=" * 60 + "\n")

    agent_id = None
    client   = None
    core     = None

    try:
        # ── 1. Hashed SDK ─────────────────────────────────────────────────
        core = await setup_hashed()
        await configure_policies(core)

        # ── 2. Activate Hashed-protected tools ────────────────────────────
        # init_tools(core) activates all @_guard decorators in tools.py
        # Same pattern as: @core.guard("tool_name") at module level
        init_tools(core)
        print(f"🛠️  Tools activated: {list(TOOLS.keys())}\n")

        # ── 3. Azure AI Agents client ──────────────────────────────────────
        print("☁️  Connecting to Azure AI Agents...")
        client = build_client()
        print("   Client: ✅ connected\n")

        # ── 4. Build toolset (FunctionTool + ToolSet) ─────────────────────
        toolset, _ = build_toolset(TOOLS)
        print("🔧 ToolSet built with 4 functions\n")

        # ── 5. Create Azure AI Agent ───────────────────────────────────────
        # NOTE: In production, reuse an existing agent_id to avoid recreating
        # on every run. Store the ID in an env var or database.
        print("🤖 Creating agent on Azure...")
        model = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
        azure_agent = client.create_agent(
            model=model,
            name="MAF-Research-Agent",
            instructions="""You are a professional AI research assistant.

Your capabilities:
- Search for information on any technology or AI framework
- Analyze topics and generate structured insights
- Generate professional reports in Markdown
- Compare AI agent frameworks objectively

Guidelines:
- Always mention which tool you used for each piece of information
- Be concise but thorough
- When comparing frameworks, use the compare_frameworks tool
- Respond in the same language as the user (English or Spanish)

Security: All your tool operations are monitored by Hashed SDK.
""",
            toolset=toolset,
        )
        agent_id = azure_agent.id
        print(f"   Agent ID: {agent_id}\n")
        print(f"   Model   : {model}")
        print(f"   Tools   : search_web, analyze_data, generate_report, compare_frameworks")

        # ── 6. Run ─────────────────────────────────────────────────────────
        if args.query:
            run_single_query(client, agent_id, toolset, args.query)
        elif args.demo:
            run_demo(client, agent_id, toolset)
        else:
            run_interactive(client, agent_id, toolset)

    except ValueError as e:
        # Missing env vars — user-facing error
        print(f"\n⚙️  Configuration error: {e}")
        print("\n📋 Quick fix:")
        print("   1. cp .env.example .env")
        print("   2. Fill in AZURE_AI_AGENTS_ENDPOINT and AZURE_AI_AGENTS_KEY")
        print("   3. Run again\n")

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        raise

    finally:
        # Cleanup Azure agent (optional — comment out to reuse across runs)
        if client and agent_id:
            try:
                client.delete_agent(agent_id)
                print(f"\n🗑️  Agent {agent_id} deleted (cleanup)")
            except Exception:
                pass

        # Shutdown Hashed Core
        if core:
            print("🔄 Shutting down Hashed Core...")
            await core.shutdown()
            print("✅ Audit log saved. Goodbye.\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted.")
