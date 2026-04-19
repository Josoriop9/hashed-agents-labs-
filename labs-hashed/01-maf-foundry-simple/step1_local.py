"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 01 — Step 1: MAF Básico                                                ║
║  Microsoft Agent Framework + Azure AI Foundry                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender los bloques básicos de MAF                               ║
║    • Agent   — el agente que procesa mensajes                                ║
║    • Client  — la conexión al LLM (aquí: Foundry)                           ║
║    • run()   — enviar un mensaje y recibir respuesta                         ║
║                                                                              ║
║  DIFERENCIA vs Lab 00:                                                       ║
║    Lab 00 → azure-ai-agents SDK (bajo nivel, run loop manual)                ║
║    Lab 01 → agent-framework (alto nivel, run loop automático)                ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    pip install -r requirements.txt                                           ║
║    cp .env.example .env  # llenar con tus valores                           ║
║    python step1_local.py                                                     ║
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


# ══════════════════════════════════════════════════════════════════════════════
# CONCEPTOS CLAVE
# ══════════════════════════════════════════════════════════════════════════════
#
#  AIProjectClient → cliente de Azure AI Foundry
#    - Maneja la autenticación y conexión al proyecto
#    - Puede usar credenciales de CLI (az login) o API key
#
#  FoundryChatClient → client de MAF que envuelve AIProjectClient
#    - Traduce las llamadas de MAF al protocolo de Foundry
#    - Lee FOUNDRY_MODEL del .env para saber qué modelo usar
#
#  Agent → el agente de MAF
#    - Recibe: client + instructions
#    - Expone: run(message) → str
#    - Internamente: maneja el loop de chat con el LLM


async def main():
    print("=" * 60)
    print("  Lab 01 — Step 1: MAF Básico")
    print("=" * 60)

    # ── 1. Crear el cliente de Foundry ────────────────────────────────────────
    #
    # AIProjectClient puede autenticarse de dos maneras:
    #   a) API key (AzureKeyCredential) → simple, sin az login
    #   b) DefaultAzureCredential       → recomendado en producción
    #
    # Aquí usamos API key para simplificar.

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    api_key  = os.getenv("AZURE_AI_AGENTS_KEY")

    if not endpoint or not api_key:
        print("❌ Falta FOUNDRY_PROJECT_ENDPOINT o AZURE_AI_AGENTS_KEY en .env")
        return

    print(f"\n🔗 Conectando a Foundry: {endpoint[:50]}...")

    async with AIProjectClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    ) as project_client:

        # ── 2. Crear el MAF client ────────────────────────────────────────────
        #
        # FoundryChatClient envuelve AIProjectClient para que MAF pueda usarlo.
        # Lee FOUNDRY_MODEL del entorno para saber qué modelo usar.

        maf_client = FoundryChatClient(project_client=project_client)

        print(f"✅ Cliente listo (modelo: {os.getenv('FOUNDRY_MODEL', 'FOUNDRY_MODEL no seteado')})")

        # ── 3. Crear el Agent ─────────────────────────────────────────────────
        #
        # Agent es el corazón de MAF.
        # - instructions: el "system prompt" del agente
        # - name: solo para logging/identificación
        # - client: quién ejecuta el LLM
        #
        # En este step: SIN tools, SIN memoria — lo más simple posible.

        agent = Agent(
            client=maf_client,
            name="AgenteFundamental",
            instructions="""Eres un asistente educativo especializado en frameworks de agentes AI.
            
Tu trabajo es explicar conceptos de manera clara y concisa.
Responde siempre en español.
Sé directo y pedagógico.""",
        )

        print("\n🤖 Agente creado. Listo para conversar.")
        print("-" * 60)

        # ── 4. Correr el agente — la línea más importante ─────────────────────
        #
        # agent.run(mensaje) → hace TODO:
        #   1. Envía el mensaje al LLM (con las instructions como system prompt)
        #   2. Espera la respuesta
        #   3. Retorna el texto de la respuesta
        #
        # No hay loop de polling, no hay threads, no hay tool dispatching.
        # MAF lo abstrae todo.

        preguntas = [
            "¿Qué es Microsoft Agent Framework (MAF) en una sola oración?",
            "¿Cuál es la diferencia entre un 'agent' y un 'LLM' en este contexto?",
        ]

        for i, pregunta in enumerate(preguntas, 1):
            print(f"\n📨 Pregunta {i}: {pregunta}")
            print()

            respuesta = await agent.run(pregunta)

            print(f"🤖 Respuesta: {respuesta}")
            print()

    print("=" * 60)
    print("  ✅ Step 1 completado")
    print()
    print("  Conceptos aprendidos:")
    print("    • AIProjectClient → conexión a Foundry con API key")
    print("    • FoundryChatClient → bridge MAF ↔ Foundry")
    print("    • Agent(client, instructions) → el agente")
    print("    • await agent.run(mensaje) → respuesta del LLM")
    print()
    print("  Siguiente: python step2_sessions.py  (conversaciones multi-turn)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
