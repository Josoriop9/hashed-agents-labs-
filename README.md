# 🤖 AI Agents Labs — Secure Agent Development with Hashed SDK

> A progressive series of hands-on labs for building AI agents with **real security and observability** — not just prompts.

Every lab uses **[Hashed SDK](https://github.com/Josoriop9/IAMandagent)** as the security layer: cryptographic agent identity, policy-based tool enforcement, and a complete audit trail of every tool call.

---

## 🎯 The Core Idea

Most AI security tutorials say: *"add 'never do X' to your system prompt."*

These labs show a different approach:

```
❌ Prompt-based:
  "NEVER send emails"
  → LLM decides
  → no audit trail
  → jailbreakable

✅ Policy-based (Hashed):
  policy: send_email → denied
  → infrastructure decides
  → full audit trail
  → cryptographically enforced
```

The audit trail only exists if the tool is **attempted**. If you block it in the prompt, there's nothing to log.

---

## 🧪 Labs

| Lab | Framework | Cloud | Status |
|-----|-----------|-------|--------|
| [00 — MAF Agent](./labs-hashed/00-maf-agent/) | Azure AI Foundry Agents | Azure Container Apps | ✅ Complete |
| 01 — Strands Agent | AWS Strands SDK | AWS Lambda / ECS | 🔜 Coming |
| 02 — CrewAI | CrewAI | Docker / Cloud Run | 🔜 Coming |
| 03 — LangChain | LangChain | Cloud Run | 🔜 Coming |
| 04 — Semantic Kernel | Semantic Kernel | Azure | 🔜 Coming |
| 05 — AutoGen | AutoGen | Docker | 🔜 Coming |
| 06 — RAG + Agents | LlamaIndex / LangChain | Any | 🔜 Coming |

---

## 🔑 Prerequisites (All Labs)

### 1. Hashed SDK

```bash
pip install hashed-sdk
hashed login
```

Get your API key at [hashed.io](https://hashed.io).

### 2. Required env vars (all labs)

```bash
HASHED_BACKEND_URL=https://iamandagent-production.up.railway.app
HASHED_API_KEY=hashed_your_api_key_here
HASHED_IDENTITY_PASSWORD=your_strong_password_here
```

Each lab has its own additional vars. See the lab's `.env.example`.

---

## 🚀 Quick Start — Lab 00

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/ai-agents-labs.git
cd ai-agents-labs/labs-hashed/00-maf-agent

# Environment
cp .env.example .env
# Edit .env with your Azure + Hashed credentials

# Install
pip install -r requirements.txt

# Configure policies
hashed policy add search_web --allow
hashed policy add send_email --deny
hashed policy add delete_data --deny
hashed policy push

# Run
streamlit run app.py
```

Then in a separate terminal:
```bash
hashed logs list
# Watch tool calls appear as the agent uses them
```

---

## 🏗️ Architecture (Lab 00)

```
Browser
  │
  ▼
Streamlit UI (app.py)
  │
  ▼
MAFAgent (agent_core.py)
  │                    │
  ▼                    ▼
Azure AI Foundry    Hashed Backend
(LLM + Agent)       (Audit + Policies)
  │
  │ REQUIRES_ACTION
  ▼
tools.py ← Hashed guards on every tool
```

---

## 📁 Repository Structure

```
ai-agents-labs/
├── README.md                   ← You are here
│
└── labs-hashed/
    ├── README.md               ← Labs overview + key concepts
    └── 00-maf-agent/           ← Lab 00: Azure AI Foundry + Hashed
        ├── README.md           ← Lab guide (start here)
        ├── app.py              ← Streamlit UI
        ├── agent_core.py       ← Agent logic
        ├── tools.py            ← Tools with Hashed guards
        ├── agent.py            ← CLI entry point
        ├── Dockerfile
        ├── requirements.txt
        ├── .env.example
        └── deploy/
            └── deploy.sh       ← One-command deploy to Azure
```

---

## 🔐 Security Philosophy

These labs are opinionated about security:

1. **Identity over API keys** — every agent has a cryptographic identity (ECC keypair)
2. **Policy over prompt** — tool permissions are declared in code, not in the system prompt
3. **Audit everything** — every tool call (allowed OR denied) is logged with agent identity
4. **Fail-safe** — if policies aren't loaded, the default is deny

---

## 📝 License

MIT — use freely, learn freely, build securely.

---

*Built with ❤️ using Azure AI Foundry, Hashed SDK, and a lot of asyncio debugging.*
