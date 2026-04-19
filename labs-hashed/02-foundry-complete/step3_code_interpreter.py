"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 02 — Step 3: Code Interpreter + Bing Grounding                         ║
║  "El agente ejecuta código Python en un sandbox de Azure"                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender las tools BUILT-IN de Foundry Agent Service              ║
║    • Code Interpreter — el LLM escribe Python → Azure lo ejecuta             ║
║    • Bing Grounding   — el agente busca en internet en tiempo real           ║
║    • Cómo habilitar estas tools y qué requieren (connections)                ║
║                                                                              ║
║  ARQUITECTURA DE TOOLS BUILT-IN:                                             ║
║    Tu código Python           ← NO ejecuta el código                        ║
║         ↓                                                                    ║
║    azure-ai-agents SDK        ← define que el agente puede usar Code         ║
║         ↓                       Interpreter                                  ║
║    Foundry Agent Service      ← aquí el LLM ESCRIBE y EJECUTA el código     ║
║         ↓                       en un sandbox seguro                         ║
║    Resultado al agente                                                        ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step3_code_interpreter.py                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os
import json

from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.agents.models import (
    CodeInterpreterTool,
    RunStatus,
)
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# ¿QUÉ ES CODE INTERPRETER?
# ══════════════════════════════════════════════════════════════════════════════
#
#  Code Interpreter = sandbox de Python manejado por Foundry.
#
#  FLUJO:
#    1. Usuario: "Analiza estas ventas y muéstrame un resumen estadístico"
#    2. LLM: "Voy a escribir Python para esto..."
#    3. LLM genera código Python
#    4. Foundry ejecuta ese código en un sandbox seguro (aislado)
#    5. Foundry retorna el output (resultados, plots base64, etc.)
#    6. LLM incorpora los resultados en su respuesta
#
#  ¿POR QUÉ EN FOUNDRY EN VEZ DE CORRER EN TU MÁQUINA?
#    - Seguridad: el código no corre en tu infraestructura
#    - Escalabilidad: múltiples usuarios simultáneos
#    - Isolation: cada run tiene su propio sandbox
#    - No necesitas Python/libraries instaladas localmente
#
#  CÓMO HABILITARLO:
#    Solo agregar CodeInterpreterTool() al agente.
#    NO necesita una Connection especial — está incluido en Foundry.


async def demo_code_interpreter(project_client: AIProjectClient) -> None:
    """
    Demo de Code Interpreter con azure-ai-agents SDK.

    Usamos SDK directo aquí porque Code Interpreter es una feature
    específica del Foundry Agent Service que se habilita al crear el agente.
    MAF lo heredará en futuras versiones con soporte nativo.
    """
    print("\n" + "─" * 60)
    print("  DEMO: Code Interpreter")
    print("─" * 60)

    agents_client = project_client.agents
    model = os.getenv("FOUNDRY_MODEL", "gpt-4o")

    # ── Datos de demo (simula datos de una startup) ───────────────────────────
    datos_ventas = {
        "enero": 45000, "febrero": 52000, "marzo": 48000,
        "abril": 61000, "mayo": 58000, "junio": 72000,
        "julio": 69000, "agosto": 75000, "septiembre": 83000,
        "octubre": 91000, "noviembre": 88000, "diciembre": 110000,
    }

    # ── Crear agente CON Code Interpreter habilitado ──────────────────────────
    #
    # CodeInterpreterTool() habilita la capacidad de ejecutar código.
    # Se pasa como lista en el parámetro `tools` del agente.
    # El agente decide cuándo usar la tool (el LLM lo determina según la pregunta).

    code_tool = CodeInterpreterTool()

    print("\n  Creando agente con Code Interpreter...")
    agent = await agents_client.create_agent(
        model=model,
        name="AnalystAgent-CodeInterpreter",
        instructions="""Eres un analista de datos para TechStartup Inc.

Cuando te den datos numéricos, SIEMPRE:
1. Usa Code Interpreter para calcular estadísticas (no calcules mentalmente)
2. Muestra el código que escribiste
3. Interpreta los resultados en español

Sé conciso en las explicaciones, detallado en el análisis.""",
        tools=code_tool.definitions,  # ← aquí se activa Code Interpreter
    )
    print(f"  ✅ Agente creado con Code Interpreter: {agent.id[:25]}...")

    # ── Crear thread y mensaje ────────────────────────────────────────────────
    thread = await agents_client.create_thread()

    datos_str = json.dumps(datos_ventas, ensure_ascii=False)
    pregunta = f"""Aquí están las ventas mensuales de TechStartup (en USD):
{datos_str}

Por favor:
1. Calcula estadísticas básicas (total, promedio, min, max, desviación estándar)
2. Identifica el mejor y peor mes
3. Calcula el crecimiento % del primero al último mes
4. Detecta si hay algún patrón estacional"""

    await agents_client.create_message(
        thread_id=thread.id,
        role="user",
        content=pregunta,
    )

    print(f"\n  📊 Pregunta enviada. El agente usará Python para calcular...")
    print(f"  (El código Python se ejecuta en el sandbox de Azure, no en tu máquina)")

    # ── Run con polling ───────────────────────────────────────────────────────
    run = await agents_client.create_run(
        thread_id=thread.id,
        agent_id=agent.id,
    )

    dots = 0
    while run.status in (RunStatus.QUEUED, RunStatus.IN_PROGRESS):
        await asyncio.sleep(1.5)
        run = await agents_client.get_run(thread_id=thread.id, run_id=run.id)
        dots += 1
        print(f"  {'.' * (dots % 4 + 1)}", end="\r")

    print()

    # ── Mostrar resultado ─────────────────────────────────────────────────────
    if run.status == RunStatus.COMPLETED:
        print("\n  ✅ Análisis completado. Respuesta del agente:")
        print("  " + "─" * 56)

        messages = agents_client.list_messages(thread_id=thread.id, order="desc")
        async for msg in messages:
            if msg.role == "assistant":
                for block in msg.content:
                    if hasattr(block, "text"):
                        # Mostrar el texto de la respuesta
                        texto = block.text.value
                        for linea in texto.split("\n"):
                            print(f"  {linea}")
                break
    else:
        print(f"\n  ❌ Run terminó con status: {run.status}")
        if hasattr(run, "last_error") and run.last_error:
            print(f"     Error: {run.last_error}")

    # Cleanup
    await agents_client.delete_agent(agent.id)
    print("\n  🗑️  Agente de demo borrado")


# ══════════════════════════════════════════════════════════════════════════════
# BING GROUNDING — búsqueda web en tiempo real
# ══════════════════════════════════════════════════════════════════════════════

async def demo_bing_grounding(project_client: AIProjectClient) -> None:
    """
    Demo de Bing Grounding.

    Bing Grounding permite que el agente busque en internet en tiempo real.
    Requiere una Bing Search Connection en el proyecto.

    DIFERENCIA vs function tool de búsqueda:
    - Function tool: tú controlas qué se busca y cómo
    - Bing Grounding: Foundry gestiona la búsqueda directamente, resultados más ricos
    """
    print("\n" + "─" * 60)
    print("  DEMO: Bing Grounding (requiere BingSearch Connection)")
    print("─" * 60)

    bing_key = os.getenv("BING_API_KEY")
    if not bing_key:
        print("\n  ⚠️  BING_API_KEY no configurada en .env")
        print("  Este demo requiere una Bing Search connection en Foundry.")
        print()
        print("  Para configurarlo:")
        print("  1. Azure Portal → Crea un recurso 'Bing Search'")
        print("  2. Copia la API key")
        print("  3. ai.azure.com → Settings → Connections → + New → Bing Search")
        print("  4. Agrega BING_API_KEY en tu .env")
        print()
        print("  En el Lab puedes omitir este demo y continuar con step4.")
        return

    try:
        from azure.ai.agents.models import BingGroundingTool

        agents_client = project_client.agents
        model = os.getenv("FOUNDRY_MODEL", "gpt-4o")

        # Obtener la connection de Bing del proyecto
        bing_connection = await project_client.connections.get("bing-search")  # nombre de tu connection

        bing_tool = BingGroundingTool(connection_id=bing_connection.id)

        agent = await agents_client.create_agent(
            model=model,
            name="WebSearchAgent-Bing",
            instructions="""Eres un investigador de mercado para TechStartup Inc.
Usa Bing para buscar información actualizada del mercado de AI en 2026.
Responde en español con datos específicos y fuentes.""",
            tools=bing_tool.definitions,
        )

        thread = await agents_client.create_thread()
        await agents_client.create_message(
            thread_id=thread.id,
            role="user",
            content="¿Cuáles son los principales frameworks de agentes AI en 2026? ¿Cuál tiene más adopción?",
        )

        run = await agents_client.create_run(thread_id=thread.id, agent_id=agent.id)

        while run.status in (RunStatus.QUEUED, RunStatus.IN_PROGRESS):
            await asyncio.sleep(1.5)
            run = await agents_client.get_run(thread_id=thread.id, run_id=run.id)

        if run.status == RunStatus.COMPLETED:
            messages = agents_client.list_messages(thread_id=thread.id, order="desc")
            async for msg in messages:
                if msg.role == "assistant":
                    for block in msg.content:
                        if hasattr(block, "text"):
                            print(f"\n  🔍 Respuesta con datos de Bing:")
                            print(f"  {block.text.value[:500]}...")
                    break

        await agents_client.delete_agent(agent.id)

    except Exception as e:
        print(f"\n  ⚠️  Error con Bing Grounding: {e}")
        print("  Verifica que tengas una BingSearch Connection en tu proyecto.")


async def main():
    print("=" * 60)
    print("  Lab 02 — Step 3: Code Interpreter + Bing Grounding")
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

        # Code Interpreter
        await demo_code_interpreter(project_client)

        # Bing Grounding
        await demo_bing_grounding(project_client)

    print("\n" + "=" * 60)
    print("  ✅ Step 3 completado")
    print()
    print("  Conceptos aprendidos:")
    print("    • Code Interpreter = sandbox Python en Azure")
    print("    • LLM escribe código → Foundry lo ejecuta → retorna resultado")
    print("    • No corre en tu máquina — corre en Azure")
    print("    • Bing Grounding = búsqueda web nativa de Foundry")
    print("    • Ambas tools son 'built-in' — no requieren tu código Python")
    print()
    print("  Siguiente: python step4_file_search.py")
    print("   → RAG automático: sube documentos, el agente los busca")


if __name__ == "__main__":
    asyncio.run(main())
