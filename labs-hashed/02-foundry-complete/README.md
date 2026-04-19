# Lab 02 — Foundry Complete: Startup AI Concierge

> **Azure AI Foundry end-to-end** — entiende cada pieza del puzzle: modelos, runtime, tools, RAG, MCP, A2A, evaluación y seguridad. Todo usando MAF como capa pro-code.

## 🗺️ El Mapa de Foundry

```
Azure AI Foundry Platform
│
├── 🏗️  INFRAESTRUCTURA               step1_explore_foundry.py
│   ├── Hub → workspace principal
│   ├── Project → tu proyecto
│   └── Connections → servicios externos (OpenAI, Bing, Storage...)
│
├── 🤖  MODELOS                         step1_explore_foundry.py
│   ├── Model Catalog → todos los modelos disponibles
│   └── Deployments → modelos que tú deployeaste (gpt-4o, DeepSeek, Phi...)
│
├── 🛠️  AGENT SERVICE (el runtime)      step2_agent_service.py
│   ├── Agents → persistentes en Azure, tienen agent_id
│   ├── Threads → conversaciones con estado
│   └── Runs → ejecuciones del agente
│
├── 🔧  TOOLS BUILT-IN                  step3_code_interpreter.py
│   ├── Code Interpreter → sandbox Python en Azure
│   └── Bing Grounding → búsqueda web en tiempo real
│
├── 📚  FILE SEARCH / RAG               step4_file_search.py
│   ├── File Upload → sube tus documentos
│   ├── Vector Store → Foundry hace chunking + embeddings
│   └── FileSearchTool → RAG automático sin código de retrieval
│
├── 🔌  MCP TOOLS                       step5_mcp_tools.py
│   ├── Function tools → el patrón base
│   └── McpToolDefinition → conectar servidores MCP a Foundry
│
├── 🤝  A2A — MULTI-AGENTE              step6_a2a.py
│   ├── Orchestrator → entiende el intent y delega
│   └── Specialists → Support, Sales, Analytics
│
├── 📊  EVALUACIONES                    step7_evaluation.py
│   ├── Dataset → preguntas + respuestas esperadas
│   ├── LLM-as-a-judge → un modelo evalúa a otro
│   └── Metrics → Relevance, Coherence, Fluency, Similarity
│
└── 🔐  HASHED (transversal)           step8_full_startup.py
    ├── Identidad → PEM del agente
    ├── Políticas → qué tools puede/no puede usar
    └── Audit trail → todo registrado
```

## 🎯 Escenario del Lab

**TechStartup Inc** — Una startup que vende una plataforma de AI Agents. Necesitan un AI Concierge para atender a sus clientes.

El agente resultante (step 8):
- 🔍 Busca información del cliente en el CRM
- 🎫 Crea tickets de soporte automáticamente
- 🤝 Delega a especialistas (soporte técnico, ventas)
- 🔐 Tiene políticas que bloquean acciones peligrosas (borrar cuentas, emails masivos)
- 📊 Se evalúa con métricas objetivas

## 📦 Setup

```bash
# 1. Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Dependencias
pip install -r requirements.txt

# 3. Configuración
cp .env.example .env
# Editar .env con tus valores
```

## 🚀 Ejecutar los steps en orden

```bash
python step1_explore_foundry.py    # ¿Qué hay en mi proyecto?
python step2_agent_service.py      # El runtime: Agent Service
python step3_code_interpreter.py   # Tool built-in: sandbox Python
python step4_file_search.py        # RAG automático con Vector Stores
python step5_mcp_tools.py          # MCP: el estándar universal
python step6_a2a.py                # Equipo de agentes especializados
python step7_evaluation.py         # Medir calidad del agente
python step8_full_startup.py       # TODO junto + Hashed
```

---

## 📚 Conceptos en detalle

### Las 3 capas del código en Foundry

```python
# Capa 1: MAF — orquestación (TÚ ESCRIBES AQUÍ)
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

agent = Agent(client=maf_client, name="...", instructions="...", tools=[...])
result = await agent.run("¿Cuánto cuesta el plan Growth?")

# Capa 2: Azure SDKs — features específicas de Foundry
from azure.ai.agents.models import CodeInterpreterTool, FileSearchTool
from azure.ai.projects.aio import AIProjectClient

# Capa 3: Foundry Platform — todo corre aquí
# (tu código nunca toca esta capa directamente)
```

### Code Interpreter — sandbox seguro
```python
from azure.ai.agents.models import CodeInterpreterTool

code_tool = CodeInterpreterTool()
agent = await agents_client.create_agent(
    model="gpt-4o",
    tools=code_tool.definitions,  # ← activar sandbox Python en Azure
)
# El LLM escribe código → Foundry lo ejecuta → retorna resultado
# Tu máquina no ejecuta nada
```

### File Search — RAG en 3 líneas
```python
from azure.ai.agents.models import FileSearchTool

# 1. Subir docs
file = await agents_client.upload_file(file=mi_pdf, purpose="assistants")
# 2. Crear Vector Store (Foundry hace chunking + embeddings)
vs = await agents_client.create_vector_store(file_ids=[file.id])
# 3. Agente con RAG automático
tool = FileSearchTool(vector_store_ids=[vs.id])
agent = await agents_client.create_agent(
    tools=tool.definitions, tool_resources=tool.resources
)
```

### MCP — el estándar universal
```python
# Crear MCP server (Python)
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("MiServer")

@mcp.tool()
def buscar_cliente(email: str) -> str:
    """Busca un cliente en el CRM."""
    return "Alice Johnson | Enterprise"

mcp.run(transport="sse")

# Conectar a Foundry
from azure.ai.agents.models import McpToolDefinition
tool = McpToolDefinition(
    server_label="crm",
    server_url="http://localhost:8000/sse",
)
```

### A2A — agentes que llaman a otros agentes
```python
# Specialist
support_agent = Agent(client=maf_client, name="SupportAgent", instructions="...")

# Orchestrator tiene una tool que ES el specialist
async def consultar_soporte(consulta: str) -> str:
    """Consulta al especialista de soporte técnico."""
    return await support_agent.run(consulta)

orchestrator = Agent(
    client=maf_client,
    tools=[consultar_soporte],  # ← el specialist como tool
)
```

### Evaluación — LLM como juez
```python
from azure.ai.evaluation import evaluate, RelevanceEvaluator

resultado = evaluate(
    data="preguntas.jsonl",  # {query, response, ground_truth}
    evaluators={"relevance": RelevanceEvaluator(model_config)},
)
# Resultado: {"relevance": 4.5}  → escala 1-5
```

### Hashed — seguridad transversal
```python
from hashed import HashedCore, load_or_create_identity

# Identidad del agente
identity = load_or_create_identity("./secrets/agent.pem", password)
core = HashedCore(config=HashedConfig(), identity=identity, agent_name="...")
await core.initialize()

# Política
core.policy_engine.add_policy("borrar_cuenta", allowed=False)

# Guard
async def _borrar_impl(email: str) -> str:
    return "Cuenta borrada"  # Nunca se ejecuta

borrar_guarded = core.guard("borrar_cuenta")(_borrar_impl)
# → PolicyViolationError si allowed=False
# → Registrado en audit trail en ambos casos
```

---

## 🗂️ Estructura

```
02-foundry-complete/
├── README.md
├── requirements.txt
├── .env.example
├── step1_explore_foundry.py    ← Hub, Project, Connections, Models
├── step2_agent_service.py      ← Agent Service: agents, threads, runs
├── step3_code_interpreter.py   ← Code Interpreter + Bing Grounding
├── step4_file_search.py        ← File Upload + Vector Store + RAG
├── step5_mcp_tools.py          ← MCP pattern + McpToolDefinition
├── step6_a2a.py                ← Orchestrator + Specialists
├── step7_evaluation.py         ← Dataset + LLM judge + metrics
└── step8_full_startup.py       ← Todo integrado + Hashed
```

Los secrets del agente (PEM) se guardan en `secrets/` — en `.gitignore`.

---

## 🔗 Recursos

- [MAF — GitHub](https://github.com/microsoft/agent-framework)
- [Azure AI Foundry](https://ai.azure.com)
- [azure-ai-agents — SDK](https://pypi.org/project/azure-ai-agents/)
- [azure-ai-evaluation — Docs](https://learn.microsoft.com/azure/ai-studio/how-to/evaluate-generative-ai-app)
- [MCP Protocol](https://modelcontextprotocol.io)
- [A2A Protocol](https://google.github.io/A2A/)
- [Hashed SDK](https://iamandagent-production.up.railway.app)

---

## ➡️ Siguiente lab

**Lab 03 — CrewAI + Hashed** *(próximamente)*
> Crea un equipo multi-agente con roles formales (researcher, writer, reviewer, critic) usando CrewAI, y protégelo con Hashed.
