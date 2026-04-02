# 🔐 Labs — Hashed SDK + AI Agents

> A progressive series of hands-on labs for building **secure, auditable AI agents** using the Hashed SDK.
> Each lab builds on the previous one.

---

## 🎯 What You'll Learn

After completing these labs, you will be able to:

- Build AI agents with **cryptographic identity** (not just API keys)
- Enforce **tool-level policies** — allow or deny specific actions
- See a **complete audit trail** of every tool call: `hashed logs list`
- Understand why **policy-based security >> prompt-based security**
- Deploy Hashed-secured agents to **production** (Azure Container Apps)

---

## 🧪 Lab Overview

| # | Lab | Stack | Time | Key Concept |
|---|-----|-------|------|-------------|
| [00](./00-maf-agent/) | **MAF Research Agent** | Azure AI Agents + Hashed | 45 min | Full production example |
| 01 *(coming)* | Strands + Hashed | AWS Strands SDK + Hashed | 30 min | Serverless agents |
| 02 *(coming)* | CrewAI + Hashed | CrewAI + Hashed | 30 min | Multi-agent security |
| 03 *(coming)* | LangChain + Hashed | LangChain + Hashed | 30 min | Chain-level policies |

---

## 🔑 Prerequisites (All Labs)

### 1. Install Hashed CLI
```bash
pip install hashed-sdk
hashed login  # get your API key from github.com/Josoriop9/IAMandagent
```

### 2. Required env vars
```bash
HASHED_BACKEND_URL=https://iamandagent-production.up.railway.app
HASHED_API_KEY=hashed_xxxxxxxxxxxxx
HASHED_IDENTITY_PASSWORD=your-password-here
```

### 3. Verify Hashed is working
```bash
hashed agent list
# Should show your agents (empty is fine for first time)

hashed logs list
# Should show recent tool calls (empty is fine for first time)
```

---

## 🧠 The Core Concept (Read This First)

### Without Hashed
```
LLM: "I'll send that email to all users..."
→ Email sent
→ 6 months later: "Did we accidentally email users?"
→ Nobody knows. No record exists.
```

### With Hashed
```
LLM: "I'll send that email..."
→ Policy: denied
→ hashed logs list: ✗ denied | send_email | My Agent
→ 6 months later: hashed logs list --tool send_email
→ Complete record. Every attempt. Whether allowed or denied.
```

### The Key Insight
```
❌ Prompt-based:  "NEVER use send_email" → LLM decides → no audit trail
✅ Policy-based:  policy: denied         → Hashed decides → full audit trail
```

**The audit trail only exists if the tool is ATTEMPTED.**
If you block it in the prompt, Hashed has nothing to log.

---

## 📁 Repository Structure

```
labs-hashed/
├── README.md              ← You are here
├── 00-maf-agent/          ← Lab 00: MAF + Azure AI Agents (complete)
│   ├── README.md          ← Lab guide for Lab 00
│   ├── app.py             ← Streamlit UI
│   ├── agent.py           ← CLI entry point
│   ├── agent_core.py      ← The agent logic (learn this!)
│   ├── tools.py           ← Tools with Hashed guards
│   ├── Dockerfile
│   └── deploy/
│       └── deploy.sh      ← One-command deploy to Azure
│
└── (01-strands/, 02-crewai/, 03-langchain/ coming soon)
```

---

## 🚀 Quick Start

```bash
# Start with Lab 00:
cd labs-hashed/00-maf-agent
cp .env.example .env
# Edit .env with your credentials

pip install -r requirements.txt
streamlit run app.py

# In a separate terminal, watch the magic:
hashed logs list
```
