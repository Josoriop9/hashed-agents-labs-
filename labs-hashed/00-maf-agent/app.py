"""
app.py — MAF Research Agent | Streamlit UI
==========================================

Run with:
    streamlit run app.py

WHAT YOU SEE:
  - Sidebar: Hashed security status (identity + active/denied policies)
  - Main area: Chat interface with message history
  - Each AI response shows which tools were called (expandable)
  - Tool calls show Hashed guard status (✅ allowed / 🚫 denied)

LEARNING VALUE:
  This UI makes the invisible visible:
  - You can SEE every tool call the agent makes
  - You can SEE Hashed enforcing policies in real time
  - You can SEE the Azure AI Agents run loop happening
"""

from typing import Optional

import streamlit as st

from agent_core import MAFAgent, ChatResponse, ToolCallRecord

# =============================================================================
# Page Config
# =============================================================================

st.set_page_config(
    page_title="MAF Research Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# Session State
# =============================================================================

def get_agent() -> MAFAgent:
    """
    Get or create the MAFAgent in session state.

    KEY CONCEPT — Streamlit session state:
      Streamlit re-runs the entire script on every user interaction.
      We use st.session_state to persist objects across re-runs.
      This is how we avoid re-creating the Azure agent on every message.
    """
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "init_error" not in st.session_state:
        st.session_state.init_error = None
    if "initializing" not in st.session_state:
        st.session_state.initializing = False
    return st.session_state.agent


def initialize_agent() -> None:
    """Initialize the agent and store it in session state."""
    st.session_state.initializing = True
    st.session_state.init_error = None
    try:
        agent = MAFAgent()
        agent.initialize()          # sync in v2 — no asyncio.run() needed
        st.session_state.agent = agent
    except Exception as e:
        st.session_state.init_error = str(e)
        st.session_state.agent = None
    finally:
        st.session_state.initializing = False


# =============================================================================
# Sidebar — Hashed Security Status
# =============================================================================

def render_sidebar(agent: Optional[MAFAgent]) -> None:
    with st.sidebar:
        st.title("🔐 Hashed Security")
        st.caption("AI Agent Identity & Policy Engine")

        st.divider()

        if agent is None:
            st.info("Agent not initialized yet.")
            return

        # Identity
        st.subheader("🪪 Identity")
        st.code(agent.identity_hex, language=None)
        st.caption("Cryptographic identity (ECC public key prefix)")

        st.divider()

        # Model
        st.subheader("🤖 Model")
        st.write(f"`{agent.model}`")
        st.caption("Azure Foundry deployment")

        st.divider()

        # Policies
        st.subheader("📋 Active Policies")

        if agent.allowed_tools:
            st.write("**✅ Allowed**")
            for tool in agent.allowed_tools:
                st.success(f"  {tool}", icon="✅")

        if agent.denied_tools:
            st.write("**🚫 Denied**")
            for tool in agent.denied_tools:
                st.error(f"  {tool}", icon="🚫")

        st.divider()

        # Stats
        st.subheader("📊 Session Stats")
        msg_count = len([m for m in st.session_state.messages if m["role"] == "user"])
        tool_count = sum(
            len(m.get("tool_calls", []))
            for m in st.session_state.messages
            if m["role"] == "assistant"
        )
        col1, col2 = st.columns(2)
        col1.metric("Messages", msg_count)
        col2.metric("Tool calls", tool_count)

        st.divider()

        # Reset
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        if st.button("🔄 Restart Agent", use_container_width=True):
            if st.session_state.agent:
                try:
                    st.session_state.agent.shutdown(delete_agent=True)  # sync in v2
                except Exception:
                    pass
            st.session_state.agent = None
            st.session_state.messages = []
            st.rerun()

        st.divider()
        st.caption("Powered by Azure AI Agents + Hashed SDK")


# =============================================================================
# Tool Call Display
# =============================================================================

def render_tool_call(tc: ToolCallRecord, index: int) -> None:
    """Render a single tool call with Hashed status."""
    icon = "✅" if tc.allowed and not tc.error else "🚫"
    label = f"{icon} `{tc.name}`"

    with st.expander(label, expanded=False):
        col1, col2 = st.columns([1, 2])

        with col1:
            st.write("**Tool**")
            st.code(tc.name, language=None)

            st.write("**Hashed Guard**")
            if tc.allowed and not tc.error:
                st.success("Allowed ✅")
            else:
                st.error("Denied 🚫")

        with col2:
            st.write("**Arguments**")
            st.json(tc.arguments)

            if tc.output:
                st.write("**Output** (first 200 chars)")
                st.text(tc.output[:200] + ("..." if len(tc.output) > 200 else ""))

            if tc.error:
                st.write("**Error**")
                st.warning(tc.error)


# =============================================================================
# Main Chat Area
# =============================================================================

def render_chat_history() -> None:
    """Display all previous messages."""
    for msg in st.session_state.messages:
        role = msg["role"]
        content = msg["content"]
        tool_calls = msg.get("tool_calls", [])

        with st.chat_message(role):
            st.markdown(content)

            # Show tool calls for assistant messages
            if role == "assistant" and tool_calls:
                st.caption(f"🔧 {len(tool_calls)} tool call(s) — click to inspect")
                for i, tc_dict in enumerate(tool_calls):
                    tc = ToolCallRecord(**tc_dict)
                    render_tool_call(tc, i)


def render_suggested_queries() -> None:
    """Show clickable example queries when chat is empty."""
    if st.session_state.messages:
        return

    st.markdown("### 💡 Try these queries")
    suggestions = [
        "🔍 Search for information about Microsoft Agent Framework",
        "📊 Analyze Azure AI Foundry as an AI platform",
        "⚖️ Compare MAF and LangChain frameworks",
        "📄 Generate a report about AI agents in 2026",
        "🔍 Search for information about CrewAI multi-agent systems",
        "📊 Analyze the Strands agent framework",
    ]

    cols = st.columns(2)
    for i, suggestion in enumerate(suggestions):
        col = cols[i % 2]
        # Strip emoji for the actual query
        query = suggestion[2:].strip()
        if col.button(suggestion, use_container_width=True, key=f"suggest_{i}"):
            st.session_state._pending_query = query
            st.rerun()


# =============================================================================
# Main App
# =============================================================================

def main() -> None:
    agent = get_agent()

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("🤖 MAF Research Agent")
    st.caption(
        "Azure AI Agents SDK + Hashed SDK — "
        f"Model: `{st.session_state.agent.model if st.session_state.agent else 'Not connected'}`"
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    render_sidebar(agent)

    # ── Initialization Banner ─────────────────────────────────────────────────
    if agent is None:
        if st.session_state.init_error:
            st.error(f"⚠️ Initialization failed: {st.session_state.init_error}")
            st.info("💡 Check your `.env` file — AZURE_AI_AGENTS_ENDPOINT and HASHED_* vars")
            if st.button("🔄 Retry"):
                st.session_state.init_error = None
                st.rerun()
            st.stop()

        elif st.session_state.initializing:
            with st.spinner("🚀 Initializing MAF Research Agent..."):
                st.info(
                    "**What's happening right now:**\n"
                    "1. 🔐 Loading Hashed identity (ECC keypair)\n"
                    "2. 📋 Configuring policies (4 allowed, 2 denied)\n"
                    "3. ☁️ Connecting to Azure Foundry\n"
                    "4. 🤖 Creating agent on Azure (DeepSeek-V3-0324)\n"
                )
                st.stop()

        else:
            # First time — auto-initialize
            st.info("🚀 Starting agent... This takes ~5 seconds on first run.")
            initialize_agent()
            st.rerun()

    # ── Chat ──────────────────────────────────────────────────────────────────
    render_suggested_queries()
    render_chat_history()

    # Handle pending query from suggestion button click
    pending = st.session_state.pop("_pending_query", None)

    # Chat input
    user_input = st.chat_input("Ask about AI frameworks, agents, RAG, multi-agent systems...")

    # Use pending query or typed input
    query = pending or user_input

    if query:
        # Add user message to history
        st.session_state.messages.append({
            "role": "user",
            "content": query,
        })

        # Display user message immediately
        with st.chat_message("user"):
            st.markdown(query)

        # Get agent response
        with st.chat_message("assistant"):
            with st.spinner("🤔 Thinking..."):
                response: ChatResponse = agent.chat(query)

            if response.success:
                st.markdown(response.message)

                # Show tool calls
                if response.tool_calls:
                    st.caption(f"🔧 {len(response.tool_calls)} tool call(s) — click to inspect")
                    for i, tc in enumerate(response.tool_calls):
                        render_tool_call(tc, i)

                # Add to history (serialize tool calls to dict for session state)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response.message,
                    "tool_calls": [
                        {
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "output": tc.output,
                            "allowed": tc.allowed,
                            "error": tc.error,
                        }
                        for tc in response.tool_calls
                    ],
                })
            else:
                st.error(f"❌ Error: {response.error}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Error: {response.error}",
                    "tool_calls": [],
                })


if __name__ == "__main__":
    main()
