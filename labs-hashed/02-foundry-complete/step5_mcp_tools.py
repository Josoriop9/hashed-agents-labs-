"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 02 — Step 5: MCP Tools                                                 ║
║  "Model Context Protocol: el estándar para conectar herramientas a agentes" ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender MCP y cómo Foundry lo soporta                           ║
║    • ¿Qué es MCP? El estándar de Anthropic adoptado por toda la industria   ║
║    • MCP en Foundry — conectar servidores MCP como tools del agente         ║
║    • Pattern: build your own MCP server + conectar a Foundry                ║
║                                                                              ║
║  ¿QUÉ ES MCP?                                                                ║
║    Model Context Protocol = protocolo estándar para exponer tools            ║
║    a agentes AI. Como HTTP para APIs, pero para agentes.                    ║
║    Creado por Anthropic, adoptado por OpenAI, Microsoft, Google, etc.       ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    pip install mcp                                                           ║
║    python step5_mcp_tools.py                                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os

from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from dotenv import load_dotenv
from typing import Annotated
from pydantic import Field

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# ¿QUÉ ES MCP?
# ══════════════════════════════════════════════════════════════════════════════
#
#  MCP = Model Context Protocol
#
#  Es el estándar (como USB para periféricos) para:
#    - EXPONER tools, recursos y datos a agentes AI
#    - CONECTAR cualquier fuente de datos a cualquier agente
#    - Sin acoplamiento entre el framework y las herramientas
#
#  ANALOGÍA:
#    Antes de MCP: cada framework (LangChain, CrewAI, MAF) tenía su propio
#                  formato de tools. Mucho código repetido.
#    Con MCP:      creas un MCP server UNA VEZ y funciona con TODOS los frameworks.
#
#  COMPONENTES:
#    MCP Server → expone tools/recursos via protocolo estándar
#    MCP Client → el agente que consume las tools del server
#
#  FOUNDRY + MCP:
#    Foundry Agent Service puede conectarse a MCP servers como tools del agente.
#    Esto significa que puedes tener un MCP server con tus datos internos
#    y conectarlo directamente a un agente de Foundry.
#
#  MCP EN LA PRÁCTICA (casos reales):
#    - MCP server que expone tu base de datos interna
#    - MCP server con acceso a tu GitHub
#    - MCP server con tu sistema de tickets (Jira, Linear)
#    - MCP server con tu ERP/CRM
#    - MCP servers públicos: filesystem, web search, GitHub, Slack...


# ══════════════════════════════════════════════════════════════════════════════
# PARTE 1: MCP CONCEPTUAL — Function Tools como "proto-MCP"
# ══════════════════════════════════════════════════════════════════════════════
#
# Antes de conectar MCP real, entendemos el patrón con function tools.
# Las function tools de MAF y las tools de MCP son CONCEPTUALMENTE iguales:
# - función con nombre
# - descripción (docstring)
# - parámetros tipados
# - retorna un resultado
#
# La diferencia: MCP las expone vía protocolo estándar (HTTP/SSE o stdio).


# Simulamos un "MCP server de CRM" con funciones Python normales
# En producción, estas funciones estarían en un servidor MCP real.

def buscar_cliente(
    email: Annotated[str, Field(description="Email del cliente a buscar en el CRM")],
) -> str:
    """
    Busca información de un cliente en el CRM de TechStartup.
    Usa cuando necesites datos de un cliente específico (nombre, plan, estado).
    """
    # En producción: llamaría a tu CRM real via API
    clientes_demo = {
        "alice@company.com": {
            "nombre": "Alice Johnson",
            "empresa": "Acme Corp",
            "plan": "Enterprise",
            "estado": "Activo",
            "uso_mensual": "8,432 runs",
            "CS_manager": "Maria González",
        },
        "bob@startup.io": {
            "nombre": "Bob Smith",
            "empresa": "StartupIO",
            "plan": "Growth",
            "estado": "Trial activo (14 días restantes)",
            "uso_mensual": "342 runs",
            "CS_manager": "N/A",
        },
    }

    cliente = clientes_demo.get(email)
    if not cliente:
        return f"Cliente con email '{email}' no encontrado en el CRM."

    return (
        f"Cliente: {cliente['nombre']} ({cliente['empresa']})\n"
        f"Plan: {cliente['plan']} | Estado: {cliente['estado']}\n"
        f"Uso mensual: {cliente['uso_mensual']}\n"
        f"CS Manager: {cliente['CS_manager']}"
    )


def crear_ticket_soporte(
    cliente_email: Annotated[str, Field(description="Email del cliente")],
    asunto: Annotated[str, Field(description="Asunto del ticket de soporte")],
    prioridad: Annotated[str, Field(description="Prioridad: 'alta', 'media', 'baja'")],
) -> str:
    """
    Crea un ticket de soporte en el sistema de TechStartup.
    Usa cuando un cliente reporta un problema o solicita ayuda.
    """
    # En producción: llamaría a Jira, Linear, o tu sistema de tickets
    import random
    ticket_id = f"TS-{random.randint(10000, 99999)}"
    return (
        f"✅ Ticket creado: {ticket_id}\n"
        f"   Cliente: {cliente_email}\n"
        f"   Asunto: {asunto}\n"
        f"   Prioridad: {prioridad}\n"
        f"   SLA: {'4h (Enterprise)' if prioridad == 'alta' else '24h'}"
    )


def obtener_metricas_uso(
    empresa: Annotated[str, Field(description="Nombre de la empresa")],
    periodo: Annotated[str, Field(description="Periodo: 'hoy', 'semana', 'mes'")],
) -> str:
    """
    Obtiene métricas de uso de la plataforma para una empresa.
    Usa para reportes de uso, detección de anomalías, o análisis de adoption.
    """
    # En producción: llamaría a tu data warehouse o analytics API
    metricas_demo = {
        "Acme Corp": {
            "hoy": "234 runs, 3 agentes activos, 98.2% success rate",
            "semana": "1,432 runs, 5 agentes únicos, 97.8% success rate",
            "mes": "8,432 runs, 8 agentes únicos, 98.1% success rate, $156 costo",
        },
        "StartupIO": {
            "hoy": "12 runs, 1 agente activo, 100% success rate",
            "semana": "87 runs, 2 agentes únicos, 95.4% success rate",
            "mes": "342 runs, 2 agentes únicos, 96.2% success rate, $12 costo",
        },
    }

    empresa_metricas = metricas_demo.get(empresa, {})
    datos = empresa_metricas.get(periodo, "No hay datos disponibles para este período")
    return f"Métricas de {empresa} ({periodo}): {datos}"


# ══════════════════════════════════════════════════════════════════════════════
# PARTE 2: DEMO — Agente MAF con "MCP tools" simuladas
# ══════════════════════════════════════════════════════════════════════════════

async def demo_maf_con_tools_crm(project_client: AIProjectClient) -> None:
    """
    Demo de agente MAF con tools que simulan un MCP server de CRM.

    Este es el PATRÓN de integración:
    - Tus tools pueden ser funciones locales O llamadas a MCP servers
    - MAF no necesita saber si la tool es local o MCP
    """
    print("\n" + "─" * 60)
    print("  DEMO: Agente MAF con CRM tools (patrón MCP)")
    print("─" * 60)

    maf_client = FoundryChatClient(project_client=project_client)

    agent = Agent(
        client=maf_client,
        name="CustomerSuccessAgent",
        instructions="""Eres el agente de Customer Success de TechStartup Inc.

Tienes acceso a herramientas del CRM y sistema de tickets.
SIEMPRE usa las tools disponibles para dar respuestas basadas en datos reales.
No inventes información sobre clientes — búscala en el CRM.

Cuando un cliente reporta un problema:
1. Busca su información en el CRM
2. Determina la prioridad según su plan (Enterprise = alta, otros = media)
3. Crea un ticket de soporte
4. Confirma al usuario con el número de ticket

Responde en español.""",
        tools=[buscar_cliente, crear_ticket_soporte, obtener_metricas_uso],
    )

    print("\n  ✅ Agente Customer Success listo con CRM tools")
    print()

    session = agent.create_session()

    escenarios = [
        "Alice Johnson (alice@company.com) me escribió. ¿Quién es y qué plan tiene?",
        "Alice reporta que su agente principal dejó de funcionar hoy. Crea un ticket urgente.",
        "Dame las métricas de uso de Acme Corp este mes.",
    ]

    for i, escenario in enumerate(escenarios, 1):
        print(f"  📨 [{i}/{len(escenarios)}] {escenario}")
        respuesta = await agent.run(escenario, session=session)
        print(f"  🤖 {respuesta}")
        print()


# ══════════════════════════════════════════════════════════════════════════════
# PARTE 3: MCP REAL — Conexión a servidor MCP con Foundry
# ══════════════════════════════════════════════════════════════════════════════

async def demo_mcp_real_foundry(project_client: AIProjectClient) -> None:
    """
    Conectar un servidor MCP REAL a Foundry Agent Service.

    Foundry soporta MCP servers como tools de agentes.
    El servidor MCP puede estar:
    - Localmente (durante desarrollo)
    - En Azure Container Apps (producción)
    - Como Azure Function

    NOTA: Este demo requiere tener un MCP server corriendo.
    """
    print("\n" + "─" * 60)
    print("  DEMO: MCP Server real con Foundry Agent Service")
    print("─" * 60)
    print()
    print("  Para conectar un MCP server a Foundry Agent Service:")
    print()
    print("  1. Crear el MCP server (Python):")
    print()
    print("     pip install mcp")
    print()
    print("     # mcp_server.py")
    print("     from mcp.server.fastmcp import FastMCP")
    print("     mcp = FastMCP('TechStartup CRM')")
    print()
    print("     @mcp.tool()")
    print("     def buscar_cliente(email: str) -> str:")
    print("         '''Busca un cliente en el CRM'''")
    print("         return f'Cliente {email}: Plan Enterprise'")
    print()
    print("     if __name__ == '__main__':")
    print("         mcp.run(transport='sse')  # SSE para HTTP")
    print()
    print("  2. Correr el servidor:")
    print("     python mcp_server.py  # expone en http://localhost:8000/sse")
    print()
    print("  3. Conectar a Foundry (azure-ai-agents):")
    print()
    print("     from azure.ai.agents.models import McpToolDefinition")
    print()
    print("     mcp_tool = McpToolDefinition(")
    print("         server_label='crm-server',")
    print("         server_url='http://localhost:8000/sse',")
    print("         allowed_tools=['buscar_cliente', 'crear_ticket'],")
    print("     )")
    print()
    print("     agent = await agents_client.create_agent(")
    print("         model=model,")
    print("         name='MCPAgent',")
    print("         tools=mcp_tool.definitions,")
    print("     )")
    print()
    print("  ─" * 29)
    print("  ¿POR QUÉ MCP?")
    print("  • Estándar adoptado: OpenAI, Anthropic, Microsoft, Google")
    print("  • Reutilizable: un server → funciona con MAF, LangChain, CrewAI")
    print("  • Ecosistema: miles de MCP servers ya disponibles (GitHub, Slack...)")
    print("  • Seguro: control granular de qué tools expones")
    print()

    # Si hay un MCP server disponible, conectarlo
    mcp_server_url = os.getenv("MCP_SERVER_URL")
    if mcp_server_url:
        print(f"\n  🔌 MCP_SERVER_URL detectada: {mcp_server_url}")
        print("  Intentando conectar...")
        try:
            from azure.ai.agents.models import McpToolDefinition
            agents_client = project_client.agents
            model = os.getenv("FOUNDRY_MODEL", "gpt-4o")

            mcp_tool = McpToolDefinition(
                server_label="startup-mcp",
                server_url=mcp_server_url,
                require_approval="never",
            )

            agent = await agents_client.create_agent(
                model=model,
                name="MCPAgent-Demo",
                instructions="Eres un asistente que usa tools del MCP server. Responde en español.",
                tools=mcp_tool.definitions,
            )
            print(f"  ✅ Agente con MCP creado: {agent.id[:25]}...")

            thread = await agents_client.create_thread()
            await agents_client.create_message(
                thread_id=thread.id, role="user",
                content="Lista las tools disponibles y prueba una.",
            )

            from azure.ai.agents.models import RunStatus
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
                                print(f"\n  🤖 {block.text.value[:400]}")
                        break

            await agents_client.delete_agent(agent.id)

        except Exception as e:
            print(f"  ⚠️  No se pudo conectar al MCP server: {e}")
    else:
        print("  (Para usar un MCP real: agrega MCP_SERVER_URL en tu .env)")


async def main():
    print("=" * 60)
    print("  Lab 02 — Step 5: MCP Tools")
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

        # Demo 1: Patrón MCP con function tools
        await demo_maf_con_tools_crm(project_client)

        # Demo 2: Cómo conectar MCP real
        await demo_mcp_real_foundry(project_client)

    print("=" * 60)
    print("  ✅ Step 5 completado")
    print()
    print("  Conceptos aprendidos:")
    print("    • MCP = estándar universal para tools de agentes AI")
    print("    • Las function tools y MCP tools son conceptualmente iguales")
    print("    • Foundry soporta McpToolDefinition para conectar MCP servers")
    print("    • 1 MCP server → funciona con MAF, LangChain, CrewAI, etc.")
    print()
    print("  Siguiente: python step6_a2a.py")
    print("   → agentes que delegan trabajo a otros agentes")


if __name__ == "__main__":
    asyncio.run(main())
