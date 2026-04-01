# 🧪 Lab 00 — MAF Research Agent
## Microsoft Agent Framework + Hashed SDK + Azure Container Apps

> **Difficulty:** Intermediate  
> **Time:** ~45 minutes  
> **Goal:** Build and deploy a full AI research agent with Hashed security policies  

---

## 🎯 What You'll Build

A Streamlit-based AI research agent that:
- Uses **Azure AI Agents** (MAF) as the LLM orchestrator
- Has **6 tools**: 4 allowed, 2 blocked by Hashed policy
- Shows a **live audit trail** in `hashed logs list`
- Is **deployed to production** via Azure Container Apps

When a user asks to send an email or delete data, the Hashed policy blocks it — and logs the attempt.

---

## 📚 What You'll Learn

| Concept | Where |
|---------|-------|
| Hashed identity (ECC keypair) | `agent_core.py → _setup_hashed()` |
| Policy engine: allow/deny | `agent_core.py → _configure_policies()` |
| Applying guards to tools | `tools.py → init_tools()` |
| Audit trail | `hashed logs list` after running the agent |
| Belt-and-suspenders with nest_asyncio | `agent_core.py → send_email()` wrapper |
| PEM persistence in containers | `deploy/deploy.sh` + `HASHED_PEM_B64` |

---

## 🏗️ Architecture

```
Browser (student or user)
        │
        ▼
┌───────────────────────────────────────┐
│   Azure Container Apps (Production)   │
│   https://maf-research-agent.xxx.io   │
│                                       │
│   ┌─────────────────────────────┐     │
│   │  Streamlit UI (app.py)      │     │
│   └───────────────┬─────────────┘     │
│                   │                   │
│   ┌───────────────▼─────────────┐     │
│   │  MAFAgent (agent_core.py)   │     │
│   └───────────────┬─────────────┘     │
└───────────────────┼───────────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
┌────────────────┐   ┌─────────────────────┐
│ Azure Foundry  │   │   Hashed Backend    │
│ (Agent + LLM)  │   │ (Audit + Policies)  │
└────────────────┘   └─────────────────────┘
         │
         │ REQUIRES_ACTION (tool call)
         ▼
┌─────────────────────────────────┐
│  tools.py (runs in container)   │
│  TOOLS["search_web"]  ← guarded │
│  TOOLS["send_email"]  ← guarded │
└─────────────────────────────────┘
```

---

## ⚡ Quick Start (Local)

### 1. Prerequisites

```bash
# Python 3.11+
pip install -r requirements.txt

# Azure CLI
brew install azure-cli
az login

# Hashed CLI
hashed login
```

### 2. Environment setup

```bash
cp .env.example .env
# Edit .env with your credentials (see below for required vars)
```

Required `.env` variables:
```bash
# Azure AI Foundry
AZURE_AI_AGENTS_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
AZURE_AI_AGENTS_KEY=your-azure-key
AZURE_OPENAI_DEPLOYMENT_NAME=DeepSeek-V3-0324

# Hashed SDK
HASHED_BACKEND_URL=https://iamandagent-production.up.railway.app
HASHED_API_KEY=hashed_xxxxxxxxxxxxx
HASHED_IDENTITY_PASSWORD=your-password
```

### 3. Configure Hashed policies

```bash
hashed policy add search_web --allow
hashed policy add analyze_data --allow
hashed policy add generate_report --allow
hashed policy add compare_frameworks --allow
hashed policy add send_email --deny
hashed policy add delete_data --deny
hashed policy push

# Verify:
hashed policy list
```

### 4. Run the agent

```bash
streamlit run app.py
# Opens at http://localhost:8501
```

### 5. See the security in action

```bash
# In another terminal, watch the audit trail:
hashed logs list

# Test an allowed tool:
# Ask: "Search for information about Microsoft Agent Framework"
# → hashed logs list shows: ✓ success | search_web | MAF Research Agent

# Test a denied tool:
# Ask: "Send an email to test@example.com"
# → Agent responds: "That action was blocked by the security policy"
# → hashed logs list shows: ✗ denied | send_email | MAF Research Agent
```

---

## 📁 Code Structure

```
00-maf-agent/
├── app.py            ← Streamlit UI — the interface students interact with
├── agent.py          ← CLI entry point (for non-UI usage)
├── agent_core.py     ← 🔑 THE MAIN FILE — read this carefully
├── tools.py          ← Tool implementations with Hashed guards
├── requirements.txt
├── Dockerfile
├── .env.example      ← Copy to .env
├── .env              ← Your credentials (gitignored)
├── secrets/          ← PEM files (gitignored)
│   └── maf_research_agent.pem
└── deploy/
    └── deploy.sh     ← One-command deploy to Azure
```

---

## 🔍 Code Walkthrough

### Step 1 — Identity (`agent_core.py → _setup_hashed()`)

```python
identity = load_or_create_identity(pem_path, password)
core = HashedCore(
    config=HashedConfig(),
    identity=identity,
    agent_name="MAF Research Agent",
    agent_type="research",
)
await core.initialize()
```

> **Key concept:** The PEM file IS the agent's identity. 
> Same PEM across restarts = same agent = policies apply.
> Different PEM = new anonymous agent = no policies = fail-open!

---

### Step 2 — Policies (`agent_core.py → _configure_policies()`)

```python
core.policy_engine.add_policy("search_web",   allowed=True)
core.policy_engine.add_policy("send_email",   allowed=False)  # ← DENIED
core.policy_engine.add_policy("delete_data",  allowed=False)  # ← DENIED
await core.push_policies_to_backend()
```

> **Key concept:** Policies are declared in code and synced to the Hashed backend.
> Even if the container restarts, the policies persist in the backend.

---

### Step 3 — Guards (`tools.py → init_tools()`)

```python
def init_tools(core) -> None:
    """Apply guards ONCE at startup. This is the magic line."""
    for tool_name, fn in _RAW_TOOLS.items():
        TOOLS[tool_name] = core.guard(tool_name)(fn)
        #                  ^^^^^^^^^^^^^^^^^^^^^^^^^
        #                  Wraps fn with Hashed enforcement
```

> **Key concept:** `core.guard("send_email")` wraps the function.
> When called → checks policy → logs to WAL → allows or denies.

---

### Step 4 — The Belt-and-Suspenders Pattern (`agent_core.py → send_email()`)

```python
def send_email(to, subject, body) -> str:
    # 1. Call guard → LOGS attempt to backend
    try:
        loop.run_until_complete(TOOLS["send_email"](to=to, ...))
    except Exception:
        pass  # nest_asyncio may swallow the exception — handled below

    # 2. Pump event loop → WAL flush
    loop.run_until_complete(asyncio.sleep(0.2))

    # 3. Local policy check (reliable fallback)
    policy = next((p for p in self.policies if p.name == "send_email"), None)
    if policy and not policy.allowed:
        return "Action denied by security policy: send_email is not permitted"
    
    return f"Email sent to {to}: {subject}"
```

> **Why two checks?** With `nest_asyncio` (needed for Streamlit), 
> exceptions from async guards don't always propagate.
> We check the guard (for logging), then check local policy (for enforcement).
> See `hashed-sdk-notes/03-bugs-and-edge-cases.md` for the full analysis.

---

## 🚀 Deploy to Azure Container Apps

```bash
./deploy/deploy.sh
# Builds image in Azure, deploys to Container Apps
# Returns: https://maf-research-agent.xxx.azurecontainerapps.io
```

**What the deploy script does:**
1. Builds Docker image using Azure Container Registry (no local Docker needed)
2. Deploys to Azure Container Apps
3. Injects all env vars including `HASHED_PEM_B64` (the PEM as a secret)
4. Returns the public HTTPS URL

---

## 💬 Example Queries to Try

```bash
# ✅ ALLOWED — These work:
"Search for information about Microsoft Agent Framework"
"Compare MAF and LangChain"
"Analyze CrewAI as a framework"
"Generate a report about AI Agents in 2026"

# ❌ DENIED — These are blocked by policy:
"Send an email to test@example.com"    → ✗ denied | send_email
"Delete all data from the database"    → ✗ denied | delete_data
```

After each denied attempt:
```bash
hashed logs list
# You'll see: ✗ denied | send_email | MAF Research Agent
```

---

## 🐛 Troubleshooting

### "Unknown" appears instead of agent name in logs
```
# Problem: Container is using a different PEM (new identity)
# Fix: Ensure HASHED_PEM_B64 env var is set correctly
az containerapp show --name maf-research-agent \
    --resource-group juan-rg-foundry \
    --query "properties.template.containers[0].env"
```

### `hashed policy list` shows "No policies found"
```bash
# You're in the wrong directory
cd labs-hashed/00-maf-agent
hashed policy list  # now it works
```

### Backend 500 errors
```bash
hashed login  # re-authenticate — JWT likely expired
```

### Denial not showing in `hashed logs list`
```bash
# Check if agent is using the right identity:
hashed agent list
# Should show: MAF Research Agent | 03ac85... | 🔴 Idle
# If "Unknown" → PEM identity issue (see above)
```

---

## 📊 Security Summary

| Tool | Policy | Why |
|------|--------|-----|
| `search_web` | ✅ Allowed | Low risk, informational |
| `analyze_data` | ✅ Allowed | Low risk, analytical |
| `generate_report` | ✅ Allowed | Low risk, generative |
| `compare_frameworks` | ✅ Allowed | Low risk, analytical |
| `send_email` | ❌ Denied | Requires human approval |
| `delete_data` | ❌ Denied | Irreversible, critical risk |

---

## 🎓 Lab Completion Checklist

```
✅ I can run the agent locally: streamlit run app.py
✅ I see "MAF Research Agent" (not "Unknown") in: hashed logs list
✅ I see ✓ success for allowed tools in logs
✅ I see ✗ denied for send_email and delete_data in logs
✅ The agent tells the user "blocked by security policy"
✅ I understand WHY we don't block tools in the system prompt
✅ (Optional) I deployed to Azure Container Apps successfully
```

---

*Part of the Hashed SDK Labs series. Next: Lab 01 — Strands + Hashed*
