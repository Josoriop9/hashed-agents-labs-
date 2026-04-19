"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 01 — Step 3: MAF Tools (Function Calling)                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender cómo el agente llama funciones Python                   ║
║    • Tools    — funciones Python que el LLM puede invocar                   ║
║    • @annotated — cómo describir los argumentos para el LLM                 ║
║    • Docstring — cómo describir CUÁNDO usar cada tool                       ║
║                                                                              ║
║  CÓMO FUNCIONA INTERNAMENTE:                                                 ║
║    1. MAF convierte tus funciones a JSON Schema                              ║
║    2. Envía el schema al LLM como "function definitions"                     ║
║    3. El LLM decide si usar una tool y con qué argumentos                   ║
║    4. MAF ejecuta la función Python y retorna el resultado al LLM            ║
║    5. El LLM genera la respuesta final con los datos de la tool              ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step3_tools.py                                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os
from typing import Annotated
from pydantic import Field

from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# DEFINICIÓN DE TOOLS
# ══════════════════════════════════════════════════════════════════════════════
#
# En MAF, las tools son funciones Python NORMALES.
# El LLM aprende cuándo usarlas a través de:
#   1. El NOMBRE de la función   → qué hace
#   2. El DOCSTRING              → cuándo usarla y qué retorna
#   3. Las TYPE ANNOTATIONS      → qué tipos de argumentos recibe
#   4. Los Field(description=)   → qué significa cada argumento
#
# NO necesitas decoradores especiales — solo código Python limpio.


def obtener_info_framework(
    nombre: Annotated[str, Field(description="Nombre del framework de agentes AI. Ej: 'maf', 'langchain', 'crewai', 'strands', 'autogen'")],
) -> str:
    """
    Obtiene información sobre un framework de agentes AI específico.
    Usa esta tool cuando el usuario pregunte sobre un framework en particular.
    Retorna descripción, lenguaje, empresa creadora y casos de uso.
    """
    frameworks = {
        "maf": {
            "nombre_completo": "Microsoft Agent Framework",
            "empresa": "Microsoft",
            "lenguaje": "Python",
            "descripcion": "Framework oficial de Microsoft para crear agentes AI. Integración nativa con Azure AI Foundry.",
            "casos_uso": ["agentes empresariales", "integración Azure", "workflows multi-agente"],
            "fortaleza": "Integración con el ecosistema Azure",
        },
        "langchain": {
            "nombre_completo": "LangChain",
            "empresa": "LangChain Inc",
            "lenguaje": "Python / JavaScript",
            "descripcion": "Framework popular para construir aplicaciones con LLMs. Gran ecosistema de integraciones.",
            "casos_uso": ["RAG", "chatbots", "pipelines de datos con LLMs"],
            "fortaleza": "Ecosistema grande, muchas integraciones",
        },
        "crewai": {
            "nombre_completo": "CrewAI",
            "empresa": "CrewAI Inc",
            "lenguaje": "Python",
            "descripcion": "Framework para orquestación de múltiples agentes con roles definidos.",
            "casos_uso": ["workflows multi-agente", "automatización de procesos", "equipos de agentes"],
            "fortaleza": "Abstracción de roles y crews de agentes",
        },
        "strands": {
            "nombre_completo": "Strands Agents",
            "empresa": "AWS / Amazon",
            "lenguaje": "Python",
            "descripcion": "Framework de AWS para agentes. Usa model-driven approach con Bedrock.",
            "casos_uso": ["integración AWS", "Bedrock", "agentes serverless"],
            "fortaleza": "Integración nativa con AWS y Bedrock",
        },
        "autogen": {
            "nombre_completo": "AutoGen",
            "empresa": "Microsoft Research",
            "lenguaje": "Python",
            "descripcion": "Framework para conversaciones multi-agente. Los agentes se comunican entre sí.",
            "casos_uso": ["investigación", "agentes que colaboran", "code generation"],
            "fortaleza": "Conversaciones entre agentes",
        },
        "semantic kernel": {
            "nombre_completo": "Semantic Kernel",
            "empresa": "Microsoft",
            "lenguaje": "Python / C# / Java",
            "descripcion": "SDK de Microsoft para integrar LLMs en aplicaciones enterprise. Multi-lenguaje.",
            "casos_uso": ["aplicaciones enterprise", "plugins", "integración en apps existentes"],
            "fortaleza": "Multi-lenguaje y enfoque enterprise",
        },
    }

    nombre_lower = nombre.lower()
    info = frameworks.get(nombre_lower, None)

    if not info:
        return f"No tengo información sobre el framework '{nombre}'. Frameworks disponibles: {', '.join(frameworks.keys())}"

    return (
        f"📚 {info['nombre_completo']} ({info['empresa']})\n"
        f"   Lenguaje: {info['lenguaje']}\n"
        f"   Descripción: {info['descripcion']}\n"
        f"   Casos de uso: {', '.join(info['casos_uso'])}\n"
        f"   Fortaleza: {info['fortaleza']}"
    )


def comparar_frameworks(
    framework_a: Annotated[str, Field(description="Primer framework a comparar")],
    framework_b: Annotated[str, Field(description="Segundo framework a comparar")],
) -> str:
    """
    Compara dos frameworks de agentes AI con puntuaciones.
    Usa esta tool cuando el usuario quiera comparar dos frameworks.
    Retorna una comparación con puntuaciones y veredicto.
    """
    criterios = {
        "maf":             {"facilidad": 7, "ecosistema": 8, "docs": 7, "azure": 10, "multilenguaje": 5},
        "langchain":       {"facilidad": 6, "ecosistema": 10, "docs": 9, "azure": 6, "multilenguaje": 8},
        "crewai":          {"facilidad": 8, "ecosistema": 7, "docs": 8, "azure": 5, "multilenguaje": 5},
        "strands":         {"facilidad": 7, "ecosistema": 6, "docs": 6, "azure": 3, "multilenguaje": 5},
        "autogen":         {"facilidad": 5, "ecosistema": 7, "docs": 8, "azure": 7, "multilenguaje": 5},
        "semantic kernel": {"facilidad": 6, "ecosistema": 7, "docs": 9, "azure": 9, "multilenguaje": 10},
    }

    a = framework_a.lower()
    b = framework_b.lower()

    scores_a = criterios.get(a, {"facilidad": 5, "ecosistema": 5, "docs": 5, "azure": 5, "multilenguaje": 5})
    scores_b = criterios.get(b, {"facilidad": 5, "ecosistema": 5, "docs": 5, "azure": 5, "multilenguaje": 5})

    total_a = sum(scores_a.values())
    total_b = sum(scores_b.values())

    ganador = framework_a if total_a >= total_b else framework_b

    lineas = [f"⚖️  {framework_a} vs {framework_b}"]
    for criterio in scores_a:
        sa = scores_a[criterio]
        sb = scores_b[criterio]
        ganador_criterio = "←" if sa > sb else ("→" if sb > sa else "=")
        lineas.append(f"   {criterio:15} {framework_a}: {sa}/10  {framework_b}: {sb}/10  {ganador_criterio}")
    lineas.append(f"   {'TOTAL':15} {framework_a}: {total_a}/50  {framework_b}: {total_b}/50")
    lineas.append(f"   🏆 Ganador: {ganador}")

    return "\n".join(lineas)


def listar_frameworks_disponibles() -> str:
    """
    Lista todos los frameworks de agentes AI disponibles en el curso.
    Usa esta tool cuando el usuario pregunte qué frameworks hay o quiera ver opciones.
    No requiere argumentos.
    """
    return """
📋 Frameworks de Agentes AI en el curso:

  1. MAF (Microsoft Agent Framework) — Microsoft
  2. LangChain                       — LangChain Inc
  3. CrewAI                          — CrewAI Inc
  4. Strands                         — AWS / Amazon
  5. AutoGen                         — Microsoft Research
  6. Semantic Kernel                 — Microsoft

Para info detallada: pregunta por cualquiera de ellos.
Para comparar: pide comparar dos frameworks específicos.
"""


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("  Lab 01 — Step 3: MAF Tools (Function Calling)")
    print("=" * 60)

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    api_key  = os.getenv("AZURE_AI_AGENTS_KEY")

    if not endpoint or not api_key:
        print("❌ Falta FOUNDRY_PROJECT_ENDPOINT o AZURE_AI_AGENTS_KEY en .env")
        return

    async with AIProjectClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    ) as project_client:

        maf_client = FoundryChatClient(project_client=project_client)

        # ── CLAVE: tools=[...] ────────────────────────────────────────────────
        # Pasamos las funciones como lista.
        # MAF las convierte a JSON Schema y las envía al LLM.
        # El LLM decide cuándo y cómo llamarlas.

        agent = Agent(
            client=maf_client,
            name="AgenteConTools",
            instructions="""Eres un experto en frameworks de agentes AI.
            
Tienes acceso a tools para buscar información sobre frameworks.
SIEMPRE usa tus tools para responder — no inventes información.
Responde en español. Sé didáctico y muestra los datos de las tools.""",
            tools=[
                obtener_info_framework,
                comparar_frameworks,
                listar_frameworks_disponibles,
            ],
        )

        print("✅ Agente con tools listo")
        print()

        # Session para mantener contexto entre preguntas
        session = agent.create_session()

        # Preguntas que ejercitan las tools
        preguntas = [
            "¿Qué frameworks de agentes AI tienes disponibles?",
            "Cuéntame sobre MAF (Microsoft Agent Framework).",
            "Compara MAF con LangChain.",
            "¿Y cuál usarías si estuviera en AWS?",  # ← el agente debe recordar el contexto
        ]

        for i, pregunta in enumerate(preguntas, 1):
            print(f"📨 [{i}/{len(preguntas)}] {pregunta}")
            respuesta = await agent.run(pregunta, session=session)
            print(f"🤖 {respuesta}")
            print()

    print("=" * 60)
    print("  ✅ Step 3 completado")
    print()
    print("  Conceptos aprendidos:")
    print("    • Tools = funciones Python normales con docstrings")
    print("    • Annotated[type, Field(description=)] → describe args al LLM")
    print("    • Agent(tools=[fn1, fn2]) → LLM elige cuándo llamarlas")
    print("    • MAF maneja el tool loop automáticamente")
    print()
    print("  Siguiente: python step4_hashed.py  (Hashed security layer)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
