"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 02 — Step 8: Full Startup AI Concierge + Hashed                        ║
║  "Todo junto: MAF + Foundry + MCP tools + A2A + Hashed"                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Integrar todas las piezas del puzzle en un agente production-    ║
║  ready para una startup, con Hashed como capa de seguridad transversal.     ║
║                                                                              ║
║  LO QUE CORRE AQUÍ:                                                          ║
║    ✅ MAF como orquestador (Agent + FoundryChatClient)                       ║
║    ✅ Foundry Agent Service como runtime                                     ║
║    ✅ Tools del CRM y analytics (patrón MCP)                                 ║
║    ✅ A2A: Orchestrator → SupportAgent + SalesAgent                          ║
║    ✅ Hashed: identidad + políticas + guards + audit trail                   ║
║                                                                              ║
║  ARQUITECTURA FINAL:                                                         ║
║                                                                              ║
║    Usuario                                                                   ║
║       ↓                                                                      ║
║    ConciergeAgent (MAF + Foundry runtime)                                    ║
║       ↓              ↓              ↓                                        ║
║    Tools CRM    SupportAgent    SalesAgent   ← A2A                          ║
║       ↓              ↓              ↓                                        ║
║    Hashed Guard  Hashed Guard  Hashed Guard  ← Seguridad                    ║
║       ↓              ↓              ↓                                        ║
║    Audit Trail (backend Hashed) ← Todo registrado                           ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step8_full_startup.py                                              ║
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
from hashed import HashedConfig, HashedCore, load_or_create_identity
from dotenv import load_dotenv

load_dotenv()

SECRETS_DIR = os.path.join(os.path.dirname(__file__), "secrets")
PEM_PATH = os.path.join(SECRETS_DIR, "startup_concierge.pem")


# ══════════════════════════════════════════════════════════════════════════════
# 1. HASHED — identidad y políticas
# ══════════════════════════════════════════════════════════════════════════════

async def setup_hashed() -> HashedCore:
    """
    Inicializa Hashed con la identidad del agente Concierge de la startup.
    """
    os.makedirs(SECRETS_DIR, exist_ok=True)

    password = os.getenv("HASHED_IDENTITY_PASSWORD", "changeme")
    identity = load_or_create_identity(PEM_PATH, password)
    config   = HashedConfig()

    core = HashedCore(
        config=config,
        identity=identity,
        agent_name="TechStartup-Concierge",
        agent_type="customer-facing",
    )
    await core.initialize()

    print(f"  🔐 Hashed: {core.agent_name} inicializado")
    print(f"     ID: {identity.public_key_hex[:20]}...")

    # Políticas de la startup
    # Estas políticas reflejan las reglas de negocio:
    # - El agente PUEDE buscar clientes, crear tickets, obtener métricas
    # - El agente NO PUEDE borrar datos ni enviar emails masivos
    politicas = [
        ("buscar_cliente",        True,  {"riesgo": "bajo",    "gdpr": "read-only"}),
        ("crear_ticket",          True,  {"riesgo": "bajo",    "max_hora": 100}),
        ("obtener_metricas",      True,  {"riesgo": "bajo",    "max_hora": 200}),
        ("escalar_a_soporte",     True,  {"riesgo": "medio",   "requiere": "plan_enterprise"}),
        ("borrar_cuenta",         False, {"riesgo": "critico", "razon": "irreversible"}),
        ("enviar_email_masivo",   False, {"riesgo": "alto",    "razon": "requiere_aprobacion_legal"}),
        ("exportar_datos_clientes", False, {"riesgo": "alto",  "razon": "gdpr_requiere_revison"}),
    ]

    for nombre, permitido, meta in politicas:
        core.policy_engine.add_policy(nombre, allowed=permitido, metadata=meta)
        estado = "✅ ALLOW" if permitido else "❌ DENY "
        print(f"     {estado} {nombre}")

    try:
        await core.push_policies_to_backend()
    except Exception:
        pass

    return core


# ══════════════════════════════════════════════════════════════════════════════
# 2. TOOLS con Hashed Guards
# ══════════════════════════════════════════════════════════════════════════════

def crear_tools_con_guards(core: HashedCore) -> list:
    """
    Crea las tools de la startup con guards de Hashed.
    Incluye tools permitidas y bloqueadas para demo del sistema de seguridad.
    """

    # ── CRM: Buscar cliente ───────────────────────────────────────────────────
    async def _buscar_cliente_impl(email: str) -> str:
        DB = {
            "alice@acme.com": "Alice Johnson | Acme Corp | Plan: Enterprise | Activo | CS: Maria G.",
            "bob@startup.io": "Bob Smith | StartupIO | Plan: Growth | Trial 14 días restantes",
        }
        return DB.get(email, f"Cliente '{email}' no encontrado en el CRM.")

    _buscar_cliente_g = core.guard("buscar_cliente")(_buscar_cliente_impl)

    def buscar_cliente(
        email: Annotated[str, Field(description="Email del cliente a buscar")],
    ) -> str:
        """Busca un cliente en el CRM. Usa para verificar identidad y plan del cliente."""
        try:
            return asyncio.get_event_loop().run_until_complete(_buscar_cliente_g(email))
        except Exception as e:
            return f"⛔ {e}"

    # ── Tickets: Crear ticket ─────────────────────────────────────────────────
    async def _crear_ticket_impl(email: str, asunto: str, prioridad: str) -> str:
        import random
        tid = f"TS-{random.randint(10000, 99999)}"
        sla = "4h" if prioridad == "alta" else "24h"
        return f"Ticket {tid} creado | {email} | '{asunto}' | Prioridad: {prioridad} | SLA: {sla}"

    _crear_ticket_g = core.guard("crear_ticket")(_crear_ticket_impl)

    def crear_ticket(
        email: Annotated[str, Field(description="Email del cliente")],
        asunto: Annotated[str, Field(description="Descripción del problema")],
        prioridad: Annotated[str, Field(description="'alta', 'media', o 'baja'")],
    ) -> str:
        """Crea un ticket de soporte. Usa cuando el cliente reporte un problema."""
        try:
            return asyncio.get_event_loop().run_until_complete(_crear_ticket_g(email, asunto, prioridad))
        except Exception as e:
            return f"⛔ {e}"

    # ── BLOQUEADA: Borrar cuenta ──────────────────────────────────────────────
    async def _borrar_cuenta_impl(email: str) -> str:
        return f"Cuenta {email} borrada."  # Nunca se ejecuta

    _borrar_cuenta_g = core.guard("borrar_cuenta")(_borrar_cuenta_impl)

    def borrar_cuenta(
        email: Annotated[str, Field(description="Email de la cuenta a borrar")],
    ) -> str:
        """Borra la cuenta de un cliente. ACCIÓN BLOQUEADA por política de seguridad."""
        try:
            return asyncio.get_event_loop().run_until_complete(_borrar_cuenta_g(email))
        except Exception as e:
            return f"⛔ Acción bloqueada por Hashed: {e}"

    return [buscar_cliente, crear_ticket, borrar_cuenta]


# ══════════════════════════════════════════════════════════════════════════════
# 3. A2A Specialists (también con Hashed via shared core)
# ══════════════════════════════════════════════════════════════════════════════

def crear_specialists(maf_client, core: HashedCore) -> tuple:
    """
    Crea los agentes especializados.
    En un sistema real, cada specialist tendría su PROPIO core y PEM.
    Para simplificar el demo, comparten el core del Concierge.
    """

    # Support specialist
    async def _escalar_soporte_impl(caso: str) -> str:
        return f"Caso escalado al equipo Senior: '{caso}'. Response time: 4h."

    _escalar_g = core.guard("escalar_a_soporte")(_escalar_soporte_impl)

    def escalar_a_soporte(
        caso: Annotated[str, Field(description="Descripción del caso a escalar")],
    ) -> str:
        """Escala un caso crítico al equipo de soporte senior."""
        try:
            return asyncio.get_event_loop().run_until_complete(_escalar_g(caso))
        except Exception as e:
            return f"⛔ {e}"

    support_agent = Agent(
        client=maf_client,
        name="SupportSpecialist",
        instructions="""Eres el especialista de soporte técnico de TechStartup.
Diagnostica problemas, da pasos de troubleshooting y escala cuando sea necesario.
Responde en español. Sé técnico y preciso.""",
        tools=[escalar_a_soporte],
    )

    sales_agent = Agent(
        client=maf_client,
        name="SalesSpecialist",
        instructions="""Eres el especialista de ventas de TechStartup.
Precios: Starter $49, Growth $199, Enterprise personalizado.
Ofrece demos para Enterprise. Descuento 20% anual en upgrades.
Responde en español. Sé persuasivo pero honesto.""",
    )

    return support_agent, sales_agent


# ══════════════════════════════════════════════════════════════════════════════
# 4. ORCHESTRATOR — todo junto
# ══════════════════════════════════════════════════════════════════════════════

def crear_concierge(maf_client, tools: list, support: Agent, sales: Agent) -> Agent:
    """El agente principal con tools + A2A."""

    async def consultar_soporte(
        consulta: Annotated[str, Field(description="El problema técnico del cliente")],
    ) -> str:
        """Consulta al especialista de soporte. Usa para problemas técnicos."""
        r = await support.run(consulta)
        return f"[SupportSpecialist]: {r}"

    async def consultar_ventas(
        consulta: Annotated[str, Field(description="Pregunta sobre planes o precios")],
    ) -> str:
        """Consulta al especialista de ventas. Usa para preguntas de pricing."""
        r = await sales.run(consulta)
        return f"[SalesSpecialist]: {r}"

    return Agent(
        client=maf_client,
        name="ConciergeAgent",
        instructions="""Eres el AI Concierge de TechStartup Inc.

ROUTING:
- Datos del cliente → buscar_cliente
- Problemas técnicos → consultar_soporte (y luego crear_ticket)
- Precios/planes → consultar_ventas
- Solicitar borrar cuenta → usa borrar_cuenta (estará bloqueada — informar al cliente)

COMPORTAMIENTO:
1. Identifica el intent
2. Usa las tools en el orden correcto
3. Informa transparentemente qué herramienta usaste
4. Si algo está bloqueado, explica que la política de seguridad lo impide

Responde en español. Eres el punto de contacto principal de la startup.""",
        tools=tools + [consultar_soporte, consultar_ventas],
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("  Lab 02 — Step 8: Full Startup AI Concierge + Hashed")
    print("=" * 60)

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    api_key  = os.getenv("AZURE_AI_AGENTS_KEY")

    if not endpoint or not api_key:
        print("❌ Falta FOUNDRY_PROJECT_ENDPOINT o AZURE_AI_AGENTS_KEY en .env")
        return
    if not os.getenv("HASHED_API_KEY"):
        print("❌ Falta HASHED_API_KEY en .env")
        return

    # ── 1. Setup Hashed ───────────────────────────────────────────────────────
    print("\n🔐 Inicializando Hashed...")
    core = await setup_hashed()

    # ── 2. Crear tools con guards ─────────────────────────────────────────────
    tools_guarded = crear_tools_con_guards(core)
    print(f"\n🛠️  {len(tools_guarded)} tools con Hashed guards")

    # ── 3. Crear agentes ──────────────────────────────────────────────────────
    async with AIProjectClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    ) as project_client:

        maf_client = FoundryChatClient(project_client=project_client)

        support_agent, sales_agent = crear_specialists(maf_client, core)
        concierge = crear_concierge(maf_client, tools_guarded, support_agent, sales_agent)

        print("\n✅ Startup AI Concierge listo:")
        print("   ConciergeAgent")
        print("   ├── buscar_cliente    [Hashed: ALLOW]")
        print("   ├── crear_ticket      [Hashed: ALLOW]")
        print("   ├── borrar_cuenta     [Hashed: DENY]  ← demo seguridad")
        print("   ├── SupportSpecialist [A2A]")
        print("   └── SalesSpecialist   [A2A]")
        print()

        session = concierge.create_session()

        # Conversación que ejercita TODAS las piezas
        conversacion = [
            "Hola, soy Alice de Acme Corp (alice@acme.com). Nuestro agente de producción dio error 503 esta mañana.",
            "¿Qué plan tenemos y qué soporte nos corresponde?",
            "Necesito explorar un upgrade a Enterprise. ¿Cuánto cuesta?",
            "Quiero borrar mi cuenta de TechStartup.",  # ← BLOQUEADA por Hashed
        ]

        for i, mensaje in enumerate(conversacion, 1):
            print(f"{'─' * 60}")
            print(f"👤 [{i}/{len(conversacion)}] {mensaje}")
            print()
            respuesta = await concierge.run(mensaje, session=session)
            print(f"🤖 {respuesta}")
            print()

    # ── 4. Audit trail ────────────────────────────────────────────────────────
    print("─" * 60)
    print("  📊 AUDIT TRAIL en Hashed:")
    print()
    print("  $ hashed logs list")
    print()
    print("  Deberías ver 4 entradas:")
    print("    ✓ buscar_cliente       → allowed")
    print("    ✓ crear_ticket         → allowed")
    print("    ✓ consultar_soporte    → allowed (A2A)")
    print("    ✗ borrar_cuenta        → DENIED  ← seguridad funcionando")

    # ── 5. Shutdown ───────────────────────────────────────────────────────────
    await core.shutdown()

    print("\n" + "=" * 60)
    print("  🎉 Lab 02 completado — Foundry End-to-End")
    print()
    print("  El puzzle completo:")
    print("    MAF         → orquestación del agente")
    print("    Foundry     → runtime (Agent Service) + modelos")
    print("    Code Interp → sandbox Python (step 3)")
    print("    File Search → RAG automático (step 4)")
    print("    MCP         → tools estándar (step 5)")
    print("    A2A         → equipo de agentes especializados (step 6)")
    print("    Evaluation  → calidad medible (step 7)")
    print("    Hashed      → seguridad, identidad y audit trail")
    print()
    print("  Ahora eres un DURO en Foundry 🚀")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
