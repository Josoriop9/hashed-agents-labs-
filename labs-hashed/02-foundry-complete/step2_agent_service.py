"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 02 — Step 2: Foundry Agent Service con MAF                             ║
║  "El agente vive en Azure — no en tu máquina"                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender el Foundry Agent Service como runtime                   ║
║    • Agent Service vs Inference directa — cuándo usar cada uno              ║
║    • Agente PERSISTENTE — el agent_id que no cambia                          ║
║    • Threads — conversaciones con estado en Azure                            ║
║    • MAF + FoundryChatClient — la capa pro-code encima del Agent Service     ║
║                                                                              ║
║  DOS ENFOQUES (los comparamos en este step):                                 ║
║    Approach A: MAF (alto nivel, menos código, más abstracción)               ║
║    Approach B: azure-ai-agents directo (bajo nivel, más control)             ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step2_agent_service.py                                             ║
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
# ¿QUÉ ES EL FOUNDRY AGENT SERVICE?
# ══════════════════════════════════════════════════════════════════════════════
#
#  INFERENCE DIRECTA (sin Agent Service):
#    Tu código → llama al modelo → respuesta → fin.
#    No hay estado, no hay historial, cada llamada es independiente.
#    Usa: azure-ai-inference, openai SDK
#
#  FOUNDRY AGENT SERVICE (con Agent Service):
#    Tu código → Agent en Azure → Threads (historial) → Runs (ejecuciones)
#    El agente VIVE en Azure. Tiene:
#      - Nombre, instrucciones, modelo → definidos una vez, persisten
#      - Threads → conversaciones con historial completo en Azure
#      - Runs → cada ejecución puede invocar tools, verificar políticas, etc.
#
#  ¿CUÁNDO USAR AGENT SERVICE?
#    ✓ Necesitas estado/historial en Azure (no en tu máquina)
#    ✓ Necesitas tools avanzadas: Code Interpreter, File Search
#    ✓ Tu app escala (múltiples usuarios, conversaciones simultáneas)
#    ✓ Necesitas persistencia entre deployments de tu app
#
#  ¿CUÁNDO USAR INFERENCE DIRECTA?
#    ✓ Casos simples (una pregunta, una respuesta)
#    ✓ Quieres mínima latencia sin overhead del Agent Service
#    ✓ Construyes tu propio loop de chat


# ══════════════════════════════════════════════════════════════════════════════
# APPROACH A: MAF con FoundryChatClient (RECOMENDADO para pro code)
# ══════════════════════════════════════════════════════════════════════════════

async def demo_maf_approach(project_client: AIProjectClient) -> None:
    """
    APPROACH A: MAF como capa de orquestación.

    MAF usa FoundryChatClient que internamente:
    1. Llama al Agent Service de Foundry
    2. Crea threads automáticamente
    3. Maneja el run loop
    4. Retorna el resultado limpio

    VENTAJA: menos código, más legible, mejor para escalar.
    """
    print("\n" + "─" * 60)
    print("  APPROACH A: MAF + FoundryChatClient")
    print("  (alto nivel, recomendado para pro code)")
    print("─" * 60)

    maf_client = FoundryChatClient(project_client=project_client)

    # ── Crear el agente con MAF ───────────────────────────────────────────────
    #
    # El Agent de MAF se conecta al Foundry Agent Service.
    # Cuando llamas agent.run(), MAF:
    #   1. Crea un Thread en Foundry (si no existe)
    #   2. Agrega el mensaje al Thread
    #   3. Crea un Run
    #   4. Espera a que el Run termine
    #   5. Retorna la respuesta del agente

    agent = Agent(
        client=maf_client,
        name="StartupConcierge-MAF",
        instructions="""Eres el AI Concierge de TechStartup Inc.
        
Ayudas a los usuarios con preguntas sobre el producto, soporte y onboarding.
Eres amable, conciso y profesional.
Responde siempre en español.""",
    )

    print("\n✅ Agente creado con MAF")
    print("   El agente usa Foundry Agent Service como runtime.")
    print()

    # Conversación multi-turn con session
    session = agent.create_session()

    mensajes = [
        "Hola, soy nuevo usuario de TechStartup. ¿Qué hace su producto?",
        "¿Cómo configuro mi cuenta?",
        "¿Qué soporte tienen disponible?",
    ]

    for i, msg in enumerate(mensajes, 1):
        print(f"  👤 [{i}/{len(mensajes)}] {msg}")
        respuesta = await agent.run(msg, session=session)
        print(f"  🤖 {respuesta}")
        print()


# ══════════════════════════════════════════════════════════════════════════════
# APPROACH B: azure-ai-agents directo (bajo nivel, para referencia)
# ══════════════════════════════════════════════════════════════════════════════

async def demo_sdk_directo(project_client: AIProjectClient) -> None:
    """
    APPROACH B: azure-ai-agents SDK directamente.

    Aquí ves lo que MAF abstrae para ti.
    Es útil para entender lo que pasa "bajo el capó" y para casos
    donde necesitas control granular sobre threads y runs.
    """
    import time

    print("\n" + "─" * 60)
    print("  APPROACH B: azure-ai-agents SDK directo")
    print("  (bajo nivel, para ver lo que MAF abstrae)")
    print("─" * 60)

    agents_client = project_client.agents
    model = os.getenv("FOUNDRY_MODEL", "gpt-4o")

    # ── 1. Crear el agente (PERSISTE en Azure) ────────────────────────────────
    print("\n  Paso 1: Crear agente en Foundry...")
    agent = await agents_client.create_agent(
        model=model,
        name="StartupConcierge-SDK",
        instructions="""Eres el AI Concierge de TechStartup Inc.
Responde siempre en español. Sé conciso.""",
    )
    print(f"  ✅ Agente creado: id={agent.id[:30]}...")
    print(f"     ESTE ID PERSISTE EN AZURE — puedes reutilizarlo")

    # ── 2. Crear un Thread ────────────────────────────────────────────────────
    #
    # Thread = una conversación con historial.
    # Puedes tener múltiples threads por agente (uno por usuario, por sesión, etc.)
    print("\n  Paso 2: Crear Thread (conversación)...")
    thread = await agents_client.create_thread()
    print(f"  ✅ Thread creado: id={thread.id[:30]}...")
    print(f"     El Thread guarda el historial de mensajes en Azure")

    # ── 3. Enviar un mensaje al Thread ────────────────────────────────────────
    print("\n  Paso 3: Enviar mensaje al Thread...")
    await agents_client.create_message(
        thread_id=thread.id,
        role="user",
        content="¿Cuál es el principal beneficio de TechStartup?",
    )
    print("  ✅ Mensaje añadido al Thread")

    # ── 4. Crear un Run ───────────────────────────────────────────────────────
    #
    # Run = una ejecución del agente sobre el Thread.
    # El agente lee el historial y genera una respuesta.
    print("\n  Paso 4: Crear Run (ejecución del agente)...")
    run = await agents_client.create_run(
        thread_id=thread.id,
        agent_id=agent.id,
    )
    print(f"  ✅ Run creado: id={run.id[:30]}...")

    # ── 5. Esperar a que termine el Run ───────────────────────────────────────
    #
    # Los Runs son ASÍNCRONOS en Foundry — hay que hacer polling.
    # MAF hace esto automáticamente con agent.run().
    # Aquí lo hacemos manual para ver el proceso.
    print("\n  Paso 5: Esperar resultado (polling)...")
    from azure.ai.agents.models import RunStatus
    while run.status in (RunStatus.QUEUED, RunStatus.IN_PROGRESS):
        await asyncio.sleep(1)
        run = await agents_client.get_run(thread_id=thread.id, run_id=run.id)
        print(f"     Status: {run.status}...")

    # ── 6. Leer la respuesta ──────────────────────────────────────────────────
    if run.status == RunStatus.COMPLETED:
        messages = agents_client.list_messages(thread_id=thread.id, order="desc")
        async for msg in messages:
            if msg.role == "assistant":
                for block in msg.content:
                    if hasattr(block, "text"):
                        print(f"\n  🤖 Respuesta: {block.text.value}")
                break

    # ── 7. Cleanup ────────────────────────────────────────────────────────────
    # En producción: GUARDAR el agent.id para reutilizarlo.
    # Para este demo: lo borramos para no acumular agentes.
    await agents_client.delete_agent(agent.id)
    print(f"\n  🗑️  Agente de demo borrado (en producción: guardar el agent_id)")


# ══════════════════════════════════════════════════════════════════════════════
# COMPARACIÓN VISUAL
# ══════════════════════════════════════════════════════════════════════════════

def mostrar_comparacion():
    print("\n" + "═" * 60)
    print("  COMPARACIÓN: MAF vs SDK Directo")
    print("═" * 60)
    print()
    print("  Misma operación, diferente abstracción:")
    print()
    print("  SDK DIRECTO (azure-ai-agents):")
    print("    agent = await agents_client.create_agent(...)")
    print("    thread = await agents_client.create_thread()")
    print("    await agents_client.create_message(thread_id=..., ...)")
    print("    run = await agents_client.create_run(thread_id=..., agent_id=...)")
    print("    while run.status in (QUEUED, IN_PROGRESS): ← polling manual")
    print("        await asyncio.sleep(1)")
    print("        run = await agents_client.get_run(...)")
    print("    # leer messages, extraer texto...")
    print()
    print("  MAF (agent-framework):")
    print("    agent = Agent(client=maf_client, instructions=...)")
    print("    session = agent.create_session()")
    print("    respuesta = await agent.run(mensaje, session=session)  ← TODO")
    print()
    print("  MAF abstrae: thread creation, message posting, polling,")
    print("               run management, response extraction.")


async def main():
    print("=" * 60)
    print("  Lab 02 — Step 2: Foundry Agent Service con MAF")
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

        # Demo A: MAF (recomendado)
        await demo_maf_approach(project_client)

        # Demo B: SDK directo (para entender qué abstrae MAF)
        print("\n" + "─" * 60)
        print("  ¿Quieres ver el enfoque de bajo nivel (azure-ai-agents)?")
        respuesta = input("  Correr Approach B? (s/n): ").strip().lower()
        if respuesta == "s":
            await demo_sdk_directo(project_client)

    # Comparación final
    mostrar_comparacion()

    print()
    print("  ✅ Step 2 completado")
    print()
    print("  Conceptos aprendidos:")
    print("    • Foundry Agent Service = el runtime para agentes")
    print("    • Agents son PERSISTENTES (tienen agent_id en Azure)")
    print("    • Threads = conversaciones con estado en la nube")
    print("    • Runs = ejecuciones del agente dentro de un thread")
    print("    • MAF abstrae agent+thread+run en agent.run()")
    print()
    print("  Siguiente: python step3_code_interpreter.py")
    print("   → el agente ejecuta código Python real en Azure")


if __name__ == "__main__":
    asyncio.run(main())
