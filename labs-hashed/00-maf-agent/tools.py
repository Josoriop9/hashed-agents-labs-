"""
tools.py — MAF Research Agent Tools
=====================================

PATTERN — Identical to the Hashed template:

    # Template (synchronous core init):
    core = HashedCore(...)

    @core.guard("tool_name")
    async def my_tool(arg: str) -> dict:
        ...

    # Our pattern (async core init via init_tools):
    async def my_tool(arg: str) -> dict:
        ...

    def init_tools(core):
        TOOLS["my_tool"] = core.guard("my_tool")(my_tool)  # guard applied ONCE

KEY DIFFERENCE FROM LAZY APPROACH:
  Guards are applied ONCE at init_tools() time — NOT recreated on every call.
  This ensures the Hashed SDK's audit tracking (success + denied events)
  work exactly like @core.guard() at module level.

SECURITY FLOW:
  caller → TOOLS["search_web"](query)
               │
               ▼
           core.guard("search_web") runs  ← created ONCE in init_tools()
               │
        ┌──────┴──────┐
        ▼             ▼
    ✅ ALLOWED     🚫 DENIED
    executes       policy blocks
    logs success   logs denial  ← both appear in hashed logs list
"""

from datetime import datetime


# =============================================================================
# Raw tool functions — NO guard decorators here
# Guards are applied once in init_tools() below
# =============================================================================

async def search_web(query: str) -> dict:
    """
    Search for information on the web (simulated).
    Policy: allowed=True, max_per_hour=20

    In production, replace with: Bing Search, Tavily, or SerpAPI
    """
    print(f"  🔍 [search_web] query='{query}'")

    knowledge_base = {
        "azure": [
            "Azure AI Foundry is Microsoft's platform for AI/ML workloads.",
            "Azure Agent Service hosts agents as managed containers.",
            "Azure OpenAI supports GPT-4o, DeepSeek, and Llama via Azure Foundry.",
        ],
        "maf": [
            "Microsoft Agent Framework supports graph-based agent workflows.",
            "MAF allows orchestrating multiple agents with checkpointing.",
            "MAF includes a built-in DevUI for debugging agent behavior.",
        ],
        "hashed": [
            "Hashed SDK provides cryptographic identities for AI agents.",
            "Hashed policy engine controls which operations each agent can perform.",
            "Hashed audit log records all agent operations for compliance.",
        ],
        "langchain": [
            "LangChain is the most widely used framework for LLM applications.",
            "LangChain provides built-in memory management and RAG support.",
            "LangChain supports multiple LLM providers through a unified API.",
        ],
        "crewai": [
            "CrewAI specializes in multi-agent teams with defined roles.",
            "CrewAI uses a crew + task model for agent collaboration.",
            "CrewAI is beginner-friendly for building agent workflows.",
        ],
        "autogen": [
            "AutoGen (Microsoft) enables multi-agent conversations.",
            "AutoGen supports human-in-the-loop workflows natively.",
            "AutoGen v0.4 introduces async actor-based agents.",
        ],
        "strands": [
            "Strands is an AWS open-source agent framework (2025).",
            "Strands uses a model-driven loop: model decides what tools to call.",
            "Strands Labs provides production-ready agent templates.",
        ],
        "rag": [
            "RAG (Retrieval Augmented Generation) grounds LLMs in external data.",
            "RAG uses a vector store to find relevant documents before generation.",
            "RAG reduces hallucinations by providing factual context.",
        ],
    }

    query_lower = query.lower()
    results = []
    for keyword, facts in knowledge_base.items():
        if keyword in query_lower:
            results.extend(facts)

    if not results:
        results = [
            f"General information about '{query}'.",
            "No specific data found in local knowledge base.",
            "Consider connecting a real search API for live results.",
        ]

    return {
        "query": query,
        "results": results[:3],
        "source": "simulated_search",
        "timestamp": datetime.utcnow().isoformat(),
    }


async def analyze_data(topic: str, depth: str = "medium") -> dict:
    """
    Analyze a topic and generate structured insights (pros/cons/trend/use cases).
    Policy: allowed=True, max_per_hour=50
    """
    print(f"  📊 [analyze_data] topic='{topic}', depth='{depth}'")

    templates = {
        "azure": {
            "pros": ["Complete ecosystem", "Enterprise security", "O365 integration"],
            "cons": ["Can be expensive at scale", "Steeper learning curve"],
            "trend": "Growing — strong focus on AI/ML 2025-2026",
            "use_cases": ["Enterprise AI", "MLOps pipelines", "Multi-agent systems"],
        },
        "maf": {
            "pros": ["Official Microsoft support", "Python and .NET", "Native Foundry deployment"],
            "cons": ["Relatively new (pre-release)", "Documentation still evolving"],
            "trend": "Emerging — rapid growth in 2026",
            "use_cases": ["Hosted agents", "Graph-based workflows", "Enterprise bots"],
        },
        "langchain": {
            "pros": ["Huge community", "Excellent RAG support", "Many integrations"],
            "cons": ["API changes frequently", "Can be heavy for simple tasks"],
            "trend": "Mature and stable — industry standard",
            "use_cases": ["RAG pipelines", "Document QA", "General purpose agents"],
        },
        "crewai": {
            "pros": ["Role-based agents", "Easy multi-agent setup", "Good documentation"],
            "cons": ["Less flexible than LangChain", "Smaller ecosystem"],
            "trend": "Growing fast — popular for multi-agent demos",
            "use_cases": ["Research teams", "Content generation", "Workflow automation"],
        },
        "autogen": {
            "pros": ["Microsoft-backed", "Strong multi-agent support", "Human-in-the-loop"],
            "cons": ["v0.4 breaking changes", "Async can be complex"],
            "trend": "Stable — widely used in enterprise",
            "use_cases": ["Code generation", "Data analysis", "Debate agents"],
        },
        "strands": {
            "pros": ["AWS-native", "Simple model-driven loop", "Open source"],
            "cons": ["AWS-centric", "Newer — smaller community"],
            "trend": "Emerging — AWS pushing it hard in 2025-2026",
            "use_cases": ["AWS Lambda agents", "Event-driven workflows", "Bedrock apps"],
        },
    }

    template = None
    for key in templates:
        if key in topic.lower():
            template = templates[key]
            break

    if not template:
        template = {
            "pros": ["Flexible", "Extensible", "Open ecosystem"],
            "cons": ["Context-dependent", "Requires setup"],
            "trend": "Positive",
            "use_cases": ["Multiple applications"],
        }

    return {
        "topic": topic,
        "depth": depth,
        "analysis": template,
        "generated_at": datetime.utcnow().isoformat(),
    }


async def generate_report(title: str, content_summary: str) -> dict:
    """
    Generate an executive research report in Markdown format.
    Policy: allowed=True, max_per_hour=10
    """
    print(f"  📄 [generate_report] title='{title}'")

    report = f"""# {title}

**Generated:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
**Agent:** MAF Research Agent (Hashed-protected)

---

## Executive Summary

{content_summary}

---

## Key Highlights

- Report generated with Microsoft Agent Framework (MAF)
- Security enforced by Hashed SDK policy engine
- Model: Azure Foundry (DeepSeek-V3 / GPT-4o)

---

## Conclusion

This report was automatically generated by an AI research agent.
All tool operations were verified against Hashed security policies.
Please verify the information before making business decisions.

---
*Powered by MAF + Hashed SDK + Azure Foundry*
"""

    return {
        "title": title,
        "report_markdown": report,
        "word_count": len(report.split()),
        "generated_at": datetime.utcnow().isoformat(),
    }


async def compare_frameworks(framework_a: str, framework_b: str) -> dict:
    """
    Compare two AI agent frameworks side by side with scores.
    Policy: allowed=True
    """
    print(f"  ⚖️  [compare_frameworks] {framework_a} vs {framework_b}")

    scores_db = {
        "ease_of_use":      {"maf": 3, "langchain": 4, "crewai": 4, "autogen": 3, "strands": 3},
        "flexibility":      {"maf": 5, "langchain": 5, "crewai": 3, "autogen": 4, "strands": 4},
        "multi_agent":      {"maf": 5, "langchain": 3, "crewai": 5, "autogen": 5, "strands": 4},
        "azure_native":     {"maf": 5, "langchain": 2, "crewai": 2, "autogen": 3, "strands": 2},
        "community_size":   {"maf": 2, "langchain": 5, "crewai": 4, "autogen": 4, "strands": 3},
        "production_ready": {"maf": 4, "langchain": 4, "crewai": 3, "autogen": 3, "strands": 4},
    }

    fa = framework_a.lower()
    fb = framework_b.lower()

    score_a = sum(dim.get(fa, 3) for dim in scores_db.values())
    score_b = sum(dim.get(fb, 3) for dim in scores_db.values())

    winner = (
        framework_a if score_a > score_b
        else framework_b if score_b > score_a
        else "Tie"
    )

    return {
        "framework_a": framework_a,
        "framework_b": framework_b,
        "scores": {framework_a: score_a, framework_b: score_b},
        "max_score": len(scores_db) * 5,
        "winner": winner,
        "dimensions": {k: {"a": v.get(fa, 3), "b": v.get(fb, 3)} for k, v in scores_db.items()},
        "verdict": (
            f"{winner} wins ({score_a} vs {score_b}/30). "
            f"Choose based on your specific requirements."
        ),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── DENIED TOOLS — Included so the LLM can ATTEMPT them ──────────────────────
# KEY TEACHING POINT:
#   For Hashed to LOG a denial, the tool must:
#   1. Exist as a function (so the LLM can call it)
#   2. Have @core.guard() applied (so Hashed can intercept and log)
#   3. Have policy allowed=False (so the guard denies and logs it)
#
#   These functions NEVER execute their body — the guard blocks them
#   BEFORE the function runs. But they MUST exist for the LLM to try calling them.

async def send_email(to: str, subject: str, body: str) -> dict:
    """
    Send an email to a recipient.
    Use when asked to send, email, notify, or contact someone.

    NOTE: This tool is controlled by Hashed security policy.
    The policy engine will automatically allow or deny this operation at runtime.
    ALWAYS call this tool when the user requests it — do not pre-screen.

    Args:
        to (str): Recipient email address
        subject (str): Email subject line
        body (str): Email message body
    Returns:
        dict: Delivery confirmation (or policy denial from Hashed guard)
    """
    # This code NEVER executes — @core.guard("send_email") with allowed=False
    # blocks execution BEFORE reaching this line, and logs the denial.
    return {"sent": True, "to": to, "subject": subject}


async def delete_data(target: str) -> dict:
    """
    Delete data, records, or files from the system.
    Use when asked to delete, remove, drop, or erase data.

    NOTE: This tool is controlled by Hashed security policy.
    The policy engine will automatically allow or deny this operation at runtime.
    ALWAYS call this tool when the user requests it — do not pre-screen.

    Args:
        target (str): The data, table, or resource to delete
    Returns:
        dict: Deletion confirmation (or policy denial from Hashed guard)
    """
    # This code NEVER executes — @core.guard("delete_data") with allowed=False
    # blocks execution BEFORE reaching this line, and logs the denial.
    return {"deleted": True, "target": target}


# =============================================================================
# TOOLS dict — populated by init_tools()
# =============================================================================

# Raw functions (no guards yet — applied once in init_tools)
_RAW_TOOLS = {
    "search_web":         search_web,
    "analyze_data":       analyze_data,
    "generate_report":    generate_report,
    "compare_frameworks": compare_frameworks,
    "send_email":         send_email,      # policy: denied
    "delete_data":        delete_data,     # policy: denied
}

# Guarded functions — populated by init_tools(core)
TOOLS: dict = {}


def init_tools(core) -> None:
    """
    Apply @core.guard() to each tool — called ONCE after core.initialize().

    This is EXACTLY equivalent to:
        @core.guard("tool_name")
        async def my_tool(...): ...

    But compatible with async initialization (core not available at import time).

    The guard is applied ONCE and stored — not recreated on each call.
    This ensures the Hashed SDK properly tracks ALL events:
        ✓ success → logged when allowed tool executes
        ✗ denied  → logged when denied tool is attempted
    """
    global TOOLS
    for tool_name, fn in _RAW_TOOLS.items():
        TOOLS[tool_name] = core.guard(tool_name)(fn)
