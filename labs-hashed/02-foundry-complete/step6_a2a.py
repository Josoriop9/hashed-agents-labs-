"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 02 — Step 6: A2A — Agent to Agent                                      ║
║  "El agente principal delega trabajo a agentes especializados"               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender orquestación multi-agente en MAF                        ║
║    • Por qué múltiples agentes especializados > un agente genérico          ║
║    • Patrón Orchestrator → Specialists con MAF                              ║
║    • A2A Protocol — el estándar emergente para comunicación entre agentes   ║
║                                                                              ║
║  ESCENARIO: Startup AI Concierge con equipo especializado                   ║
║    ConciergeAgent (orchestrator)                                             ║
║      ├── SupportAgent   → problemas técnicos, tickets                       ║
║      ├── SalesAgent     → precios, planes, upgrades                         ║
║      └── AnalyticsAgent → métricas, reportes de uso                         ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step6_a2a.py                                                       ║
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
# ¿POR QUÉ MÚLTIPLES AGENTES?
# ══════════════════════════════════════════════════════════════════════════════
#
#  PROBLEMA CON UN AGENTE GENÉRICO:
#    - Context window se llena cuando tiene demasiados instructions y tools
#    - No puede ser experto en todo al mismo tiempo
#    - Difícil de mantener cuando crece
#
#  SOLUCIÓN: ESPECIALIZACIÓN
#    - Cada agente tiene instrucciones y tools específicas para su dominio
#    - El orchestrator entiende el intent del usuario y delega
#    - Cada specialist es el "mejor" en su área
#
#  PATRONES DE ORQUESTACIÓN:
#    1. Sequential: A → B → C (resultado de uno pasa al siguiente)
#    2. Parallel: A dispara B, C, D simultáneamente → agrega resultados
#    3. Hierarchical: Orchestrator → Specialists (lo que hacemos aquí)
#    4. Collaborative: Agentes se comunican directamente entre ellos
#
#  A2A PROTOCOL:
#    Estándar emergente (Google, Microsoft) para que agentes se comuniquen.
#    Cada agente expone una "Agent Card" con sus capacidades.
#    Otros agentes descubren y llaman via HTTP estándar.
#    MAF soportará A2A protocol nativo en próximas versiones.


# ══════════════════════════════════════════════════════════════════════════════
# AGENTES ESPECIALIZADOS
# ══════════════════════════════════════════════════════════════════════════════

def crear_support_agent(maf_client) -> Agent:
    """
    SupportAgent: experto en soporte técnico y tickets.
    """
    return Agent(
        client=maf_client,
        name="SupportAgent",
        instructions="""Eres el especialista de soporte técnico de TechStartup Inc.

Tu expertise:
- Diagnóstico de problemas con agentes (errores, timeouts, bajo success rate)
- Gestión de tickets (crear, priorizar, escalar)
- Guías de troubleshooting paso a paso

PRIORIDADES:
- Enterprise: siempre prioridad ALTA, respuesta máxima 4h
- Growth: prioridad MEDIA, respuesta 24h
- Starter: prioridad BAJA, respuesta 48h

Responde en español. Sé técnico y preciso.""",
    )


def crear_sales_agent(maf_client) -> Agent:
    """
    SalesAgent: experto en precios, planes y upgrades.
    """
    return Agent(
        client=maf_client,
        name="SalesAgent",
        instructions="""Eres el especialista de ventas de TechStartup Inc.

Tu expertise:
- Explicar planes y precios (Starter $49, Growth $199, Enterprise personalizado)
- Recomendar el plan correcto según necesidades del cliente
- Gestionar upgrades y negociaciones
- ROI y casos de uso por industria

REGLAS:
- Para Enterprise: siempre ofrecer una demo personalizada
- Para upgrads desde Growth: mencionar descuento anual 20%
- NUNCA des descuentos sin aprobación del CS Manager

Responde en español. Sé persuasivo pero honesto.""",
    )


def crear_analytics_agent(maf_client) -> Agent:
    """
    AnalyticsAgent: experto en métricas y reportes.
    """
    return Agent(
        client=maf_client,
        name="AnalyticsAgent",
        instructions="""Eres el especialista de analytics de TechStartup Inc.

Tu expertise:
- Análisis de métricas de uso (runs, success rate, costos)
- Detección de anomalías y patrones
- Recomendaciones de optimización
- Reportes ejecutivos

Cuando analices datos:
1. Siempre identifica la métrica más importante primero
2. Señala tendencias (crecimiento, decline, estabilidad)
3. Termina con una recomendación accionable

Responde en español. Sé analítico y basado en datos.""",
    )


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR — El agente principal que delega
# ══════════════════════════════════════════════════════════════════════════════

def crear_orchestrator(
    maf_client,
    support_agent: Agent,
    sales_agent: Agent,
    analytics_agent: Agent,
) -> Agent:
    """
    ConciergeAgent: el orchestrator que delega a specialists.

    Las tools del orchestrator son funciones que LLAMAN a otros agentes.
    Este es el patrón A2A en MAF:
    - Cada specialist es un Agent independiente
    - El orchestrator los llama como function tools
    """

    # ── Tools = llamadas a agentes especializados ─────────────────────────────

    async def consultar_soporte(
        consulta: Annotated[str, Field(description="El problema técnico o solicitud de soporte del cliente")],
    ) -> str:
        """
        Consulta al especialista de soporte técnico.
        Usa cuando el cliente tenga problemas técnicos, errores, o necesite ayuda técnica.
        Retorna diagnóstico y pasos a seguir.
        """
        respuesta = await support_agent.run(consulta)
        return f"[SupportAgent]: {respuesta}"

    async def consultar_ventas(
        consulta: Annotated[str, Field(description="La pregunta sobre planes, precios, o upgrade")],
    ) -> str:
        """
        Consulta al especialista de ventas y planes.
        Usa cuando el cliente pregunte por precios, planes, upgrades, o comparativas.
        Retorna recomendación personalizada.
        """
        respuesta = await sales_agent.run(consulta)
        return f"[SalesAgent]: {respuesta}"

    async def consultar_analytics(
        consulta: Annotated[str, Field(description="La solicitud de métricas, reporte, o análisis")],
        datos: Annotated[str, Field(description="Datos de uso si están disponibles", default="")] = "",
    ) -> str:
        """
        Consulta al especialista de analytics y métricas.
        Usa cuando el cliente pida reportes, métricas de uso, o análisis de datos.
        Retorna análisis con recomendaciones.
        """
        mensaje = consulta if not datos else f"{consulta}\nDatos: {datos}"
        respuesta = await analytics_agent.run(mensaje)
        return f"[AnalyticsAgent]: {respuesta}"

    # ── El orchestrator ───────────────────────────────────────────────────────
    return Agent(
        client=maf_client,
        name="ConciergeAgent-Orchestrator",
        instructions="""Eres el AI Concierge principal de TechStartup Inc.

Tu función: entender lo que necesita el cliente y delegarlo al especialista correcto.

ROUTING:
- Problemas técnicos, errores, bugs → consultar_soporte
- Precios, planes, upgrades → consultar_ventas
- Métricas, reportes, datos de uso → consultar_analytics
- Temas mixtos: consulta múltiples specialists y combina sus respuestas

COMPORTAMIENTO:
1. Identifica el tipo de consulta
2. Delega al specialist correcto (o múltiples si es necesario)
3. Sintetiza la respuesta del specialist para el cliente
4. Siempre menciona qué specialist consultaste para transparencia

NO respondas desde tu propio conocimiento sobre el producto — siempre delega.
Responde en español. Sé el punto de entrada amigable y eficiente.""",
        tools=[consultar_soporte, consultar_ventas, consultar_analytics],
    )


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# ══════════════════════════════════════════════════════════════════════════════

async def demo_a2a(project_client: AIProjectClient) -> None:
    """
    Demo completo de orquestación A2A.
    """
    maf_client = FoundryChatClient(project_client=project_client)

    print("\n  🏗️  Creando equipo de agentes...")

    # Crear los 4 agentes
    support_agent   = crear_support_agent(maf_client)
    sales_agent     = crear_sales_agent(maf_client)
    analytics_agent = crear_analytics_agent(maf_client)
    orchestrator    = crear_orchestrator(maf_client, support_agent, sales_agent, analytics_agent)

    print("  ✅ Equipo listo:")
    print("     ConciergeAgent (orchestrator)")
    print("       ├── SupportAgent")
    print("       ├── SalesAgent")
    print("       └── AnalyticsAgent")
    print()

    session = orchestrator.create_session()

    # Conversación que ejercita los 3 specialists
    conversacion = [
        # → Sales Agent
        "Hola, soy el CTO de una empresa de 50 personas. ¿Qué plan nos recomiendas?",
        # → Support Agent
        "Perfecto, somos clientes de Growth. Pero hoy nuestro agente principal dio error 429. ¿Qué hacemos?",
        # → Analytics Agent
        "¿Puedes analizar estos datos de uso de este mes? Runs: 8,432. Success rate: 94%. Costo: $198.",
        # → Múltiples specialists
        "Queremos hacer upgrade a Enterprise pero necesitamos entender el ROI primero.",
    ]

    for i, mensaje in enumerate(conversacion, 1):
        print(f"  {'─'*56}")
        print(f"  👤 [{i}/{len(conversacion)}] {mensaje}")
        print()

        respuesta = await orchestrator.run(mensaje, session=session)
        print(f"  🤖 {respuesta}")
        print()


# ══════════════════════════════════════════════════════════════════════════════
# BONUS: A2A PROTOCOL ESTÁNDAR
# ══════════════════════════════════════════════════════════════════════════════

def mostrar_a2a_protocol():
    print("\n" + "═" * 60)
    print("  A2A PROTOCOL — El futuro de la comunicación entre agentes")
    print("═" * 60)
    print()
    print("  El patrón que usamos (función que llama a otro Agent) es")
    print("  la versión 'in-process' de A2A.")
    print()
    print("  A2A Protocol (estándar emergente) extiende esto a HTTP:")
    print()
    print("  Cada agente expone una 'Agent Card' (JSON):")
    print("  {")
    print('    "name": "SupportAgent",')
    print('    "description": "Especialista en soporte técnico",')
    print('    "capabilities": ["tickets", "diagnóstico"],')
    print('    "endpoint": "https://agents.techstartup.io/support"')
    print("  }")
    print()
    print("  Ventajas del A2A protocol:")
    print("  • Agentes en DIFERENTES runtimes pueden comunicarse")
    print("  • SupportAgent puede ser MAF, SalesAgent puede ser LangChain")
    print("  • Descubrimiento dinámico de agentes")
    print("  • Autenticación y autorización estándar")
    print()
    print("  Foundry soportará A2A nativo próximamente.")
    print("  Por ahora: el patrón 'Agent como función' es el equivalente.")


async def main():
    print("=" * 60)
    print("  Lab 02 — Step 6: A2A — Agent to Agent")
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
        await demo_a2a(project_client)

    mostrar_a2a_protocol()

    print("\n" + "=" * 60)
    print("  ✅ Step 6 completado")
    print()
    print("  Conceptos aprendidos:")
    print("    • Orchestrator pattern: 1 coordinador + N specialists")
    print("    • Tools del orchestrator = llamadas a otros agentes")
    print("    • Cada agent tiene contexto y expertise específico")
    print("    • A2A Protocol = extensión estándar para HTTP")
    print()
    print("  Siguiente: python step7_evaluation.py")
    print("   → evaluar la calidad del agente con Foundry Eval")


if __name__ == "__main__":
    asyncio.run(main())
