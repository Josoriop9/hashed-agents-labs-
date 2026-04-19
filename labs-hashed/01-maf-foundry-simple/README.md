# Lab 01 — MAF + Azure AI Foundry + Hashed

> **Microsoft Agent Framework** desde cero: del agente más simple hasta seguridad con Hashed en 4 pasos.

## 🎯 Qué vas a aprender

| Step | Concepto | Tiempo est. |
|------|----------|-------------|
| Step 1 | MAF básico: `Agent` + `run()` | 10 min |
| Step 2 | Sessions: conversaciones multi-turn | 10 min |
| Step 3 | Tools: function calling automático | 15 min |
| Step 4 | Hashed: identidad + políticas + audit | 20 min |

## 🆚 Diferencia vs Lab 00

| Lab 00 | Lab 01 |
|--------|--------|
| `azure-ai-agents` SDK (bajo nivel) | `agent-framework` (alto nivel) |
| Run loop manual (poll, submit_tool_outputs) | `agent.run()` abstrae todo |
| Streamlit + Docker + Container Apps | Scripts Python puros |
| Foco en el deploy | Foco en entender MAF |

## 📦 Setup

```bash
# 1. Crear virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar credenciales
cp .env.example .env
# Editar .env con tus valores reales (ver sección Variables de Entorno)
```

### Variables de entorno

Abre `.env` y llena:

```bash
# Tu proyecto de Azure AI Foundry
# Encuéntralo en: ai.azure.com → tu proyecto → Overview → Endpoints
FOUNDRY_PROJECT_ENDPOINT=https://practice-foundry-juan.services.ai.azure.com/api/projects/proj-default
AZURE_AI_AGENTS_KEY=tu_api_key_aqui

# Nombre del deployment del modelo
FOUNDRY_MODEL=DeepSeek-V3-0324  # o gpt-4o, etc.

# Solo para Step 4:
HASHED_BACKEND_URL=https://iamandagent-production.up.railway.app
HASHED_API_KEY=hashed_tu_api_key_aqui
HASHED_IDENTITY_PASSWORD=tu_password_aqui
```

## 🚀 Ejecutar los steps

```bash
# Step 1: MAF básico
python step1_local.py

# Step 2: Sessions (multi-turn)
python step2_sessions.py

# Step 3: Tools (function calling)
python step3_tools.py

# Step 4: Hashed security
python step4_hashed.py
```

---

## 📚 Conceptos en detalle

### Step 1 — MAF Básico

Los tres bloques de cualquier agente MAF:

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import AzureKeyCredential

async with AIProjectClient(endpoint=..., credential=AzureKeyCredential(key)) as project:
    client = FoundryChatClient(project_client=project)  # ← conexión al LLM

    agent = Agent(
        client=client,                    # ← quién ejecuta el LLM
        name="MiAgente",                  # ← identificación
        instructions="Eres un asistente...",  # ← system prompt
    )

    respuesta = await agent.run("¿Hola?")  # ← enviar mensaje → recibir respuesta
    print(respuesta)
```

**Por qué `FoundryChatClient`?**
- Envuelve `AIProjectClient` para que MAF pueda comunicarse con Azure AI Foundry
- Lee `FOUNDRY_MODEL` del entorno para saber qué modelo usar
- Maneja la autenticación automáticamente

---

### Step 2 — Sessions (Multi-turn)

Sin session → el agente olvida:
```python
await agent.run("Me llamo Juan")    # OK
await agent.run("¿Cómo me llamo?")  # "No sé cómo te llamas" ← olvida
```

Con session → el agente recuerda:
```python
session = agent.create_session()
await agent.run("Me llamo Juan", session=session)
await agent.run("¿Cómo me llamo?", session=session)  # "Te llamas Juan" ← recuerda
```

Múltiples sessions = múltiples usuarios aislados:
```python
session_a = agent.create_session()  # Usuario A
session_b = agent.create_session()  # Usuario B — contexto completamente separado
```

---

### Step 3 — Tools (Function Calling)

En MAF, las tools son **funciones Python normales**. No hay decoradores especiales:

```python
from typing import Annotated
from pydantic import Field

def buscar_info(
    query: Annotated[str, Field(description="La búsqueda a realizar")],
) -> str:
    """
    Busca información sobre un tema.       ← el LLM lee este docstring
    Usa cuando el usuario pida datos.      ← le dice CUÁNDO usarla
    """
    return f"Resultados para: {query}"     # ← lo que retorna al LLM

agent = Agent(client=client, tools=[buscar_info], ...)
```

**¿Cómo decide el LLM cuándo usar una tool?**
1. MAF convierte la función a JSON Schema
2. Envía el schema al LLM como "function definition"
3. El LLM lee el docstring y decide si la situación requiere usarla
4. Si decide usarla, MAF ejecuta la función Python y retorna el resultado
5. El LLM genera la respuesta final usando ese resultado

---

### Step 4 — Hashed Security

**Arquitectura:**
```
Usuario
  ↓
agent.run(mensaje)
  ↓
LLM decide llamar tool
  ↓
MAF invoca función Python
  ↓
Hashed GUARD intercepta ← aquí está la magia
  ↓              ↓
ALLOW          DENY
  ↓              ↓
ejecuta tool   bloquea + log audit
```

**Patrón de código:**
```python
from hashed import HashedConfig, HashedCore, load_or_create_identity

# 1. Identidad criptográfica del agente
identity = load_or_create_identity("./secrets/agent.pem", "mi_password")
core = HashedCore(config=HashedConfig(), identity=identity, agent_name="MiAgente", agent_type="educational")
await core.initialize()

# 2. Definir política
core.policy_engine.add_policy("buscar_info", allowed=True)
core.policy_engine.add_policy("borrar_datos", allowed=False)  # BLOQUEADA

# 3. Envolver tool con guard
async def _buscar_info_impl(query: str) -> str:
    return f"Resultados: {query}"

_buscar_guarded = core.guard("buscar_info")(_buscar_info_impl)

def buscar_info(query: str) -> str:
    """Busca información."""
    return asyncio.get_event_loop().run_until_complete(_buscar_guarded(query))

# 4. Pasar al agente
agent = Agent(client=client, tools=[buscar_info], ...)
```

**¿Por qué el PEM?**
- El PEM es la **identidad criptográfica** del agente
- Primer run: genera una clave nueva y la guarda en el PEM
- Runs siguientes: carga el PEM existente → mismo agente → mismas políticas aplicadas
- Si se pierde el PEM → nuevo agente = nueva identidad = empezar desde cero

**Ver el audit trail:**
```bash
hashed logs list        # últimas 10 acciones
hashed policy list      # políticas activas
hashed agent list       # agentes registrados
```

---

## 🗂️ Estructura del lab

```
01-maf-foundry-simple/
├── README.md              ← esta guía
├── requirements.txt       ← dependencias
├── .env.example           ← template de variables
│
├── step1_local.py         ← MAF básico (Agent + run)
├── step2_sessions.py      ← conversaciones multi-turn
├── step3_tools.py         ← function calling
└── step4_hashed.py        ← seguridad con Hashed
```

Los secrets del agente (PEM de Hashed) se guardan en `secrets/` — esta carpeta está en `.gitignore`.

---

## 🔗 Recursos

- [Microsoft Agent Framework — GitHub](https://github.com/microsoft/agent-framework)
- [Azure AI Foundry — Documentación](https://learn.microsoft.com/azure/ai-studio/)
- [Hashed SDK — Dashboard](https://iamandagent-production.up.railway.app)

---

## ➡️ Siguiente lab

**Lab 02 — CrewAI + Hashed** *(próximamente)*
> Crea un equipo de agentes con roles definidos (researcher, writer, reviewer) con seguridad Hashed en cada agente del equipo.
