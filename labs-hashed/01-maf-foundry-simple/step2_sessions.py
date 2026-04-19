"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 01 — Step 2: MAF Sessions (Conversaciones Multi-Turn)                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender cómo MAF maneja conversaciones con memoria               ║
║    • Session  — mantiene el historial de la conversación                     ║
║    • create_session() — crea un contexto de conversación                     ║
║    • agent.run(msg, session=) — respuestas que recuerdan lo anterior         ║
║                                                                              ║
║  SIN sessions: cada run() es independiente (el agente no recuerda)          ║
║  CON sessions: el agente mantiene contexto entre mensajes                    ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step2_sessions.py                                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os

from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from dotenv import load_dotenv

load_dotenv()


async def demo_sin_session(agent: Agent) -> None:
    """
    SIN session → cada llamada es independiente.
    El agente NO recuerda mensajes anteriores.
    """
    print("\n" + "─" * 60)
    print("  DEMO 1: SIN session (el agente olvida todo)")
    print("─" * 60)

    r1 = await agent.run("Mi nombre es Juan Carlos y soy de Colombia.")
    print(f"Turn 1 → {r1}\n")

    r2 = await agent.run("¿Cómo me llamo y de dónde soy?")
    print(f"Turn 2 → {r2}")
    print("\n  ⚠️  Sin session: el agente no recuerda el Turn 1")


async def demo_con_session(agent: Agent) -> None:
    """
    CON session → los mensajes se acumulan en el historial.
    El agente recuerda toda la conversación.
    """
    print("\n" + "─" * 60)
    print("  DEMO 2: CON session (el agente recuerda todo)")
    print("─" * 60)

    # create_session() → crea un objeto que guarda el historial
    # Es como abrir una pestaña de chat nueva
    session = agent.create_session()

    r1 = await agent.run("Mi nombre es Juan Carlos y soy de Colombia.", session=session)
    print(f"Turn 1 → {r1}\n")

    r2 = await agent.run("¿Cuál es mi nombre?", session=session)
    print(f"Turn 2 → {r2}\n")

    r3 = await agent.run("¿Y de qué país soy? Además, ¿qué frameworks de agentes AI conoces?", session=session)
    print(f"Turn 3 → {r3}")
    print("\n  ✅ Con session: el agente recuerda todo el contexto")


async def demo_multiples_sessions(agent: Agent) -> None:
    """
    Múltiples sesiones simultáneas → cada usuario tiene su propio contexto.
    Útil en apps multi-usuario.
    """
    print("\n" + "─" * 60)
    print("  DEMO 3: Múltiples sessions (usuarios independientes)")
    print("─" * 60)

    # Usuario A
    session_a = agent.create_session()
    await agent.run("Me llamo Ana y me interesa LangChain.", session=session_a)

    # Usuario B
    session_b = agent.create_session()
    await agent.run("Me llamo Pedro y me interesa CrewAI.", session=session_b)

    # Cada session recuerda solo su propia conversación
    r_a = await agent.run("¿Cuál es mi nombre y qué framework me interesa?", session=session_a)
    r_b = await agent.run("¿Cuál es mi nombre y qué framework me interesa?", session=session_b)

    print(f"Session A (Ana)   → {r_a}")
    print(f"Session B (Pedro) → {r_b}")
    print("\n  ✅ Cada session es independiente — perfecto para multi-usuario")


async def main():
    print("=" * 60)
    print("  Lab 01 — Step 2: MAF Sessions")
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

        # Un solo Agent, múltiples sessions
        agent = Agent(
            client=maf_client,
            name="AgenteConMemoria",
            instructions="""Eres un asistente educativo sobre frameworks de agentes AI.
Responde en español. Sé conciso (máximo 2 oraciones por respuesta).
Cuando te pregunten datos que ya se mencionaron en la conversación, cítalos.""",
        )

        print("✅ Agente listo")

        # Correr los 3 demos
        await demo_sin_session(agent)
        await demo_con_session(agent)
        await demo_multiples_sessions(agent)

    print("\n" + "=" * 60)
    print("  ✅ Step 2 completado")
    print()
    print("  Conceptos aprendidos:")
    print("    • agent.run(msg)           → sin memoria (stateless)")
    print("    • session = agent.create_session()")
    print("    • agent.run(msg, session=) → con memoria (stateful)")
    print("    • Múltiples sessions → aislamiento por usuario")
    print()
    print("  Siguiente: python step3_tools.py  (function calling)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
