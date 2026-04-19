"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 01 — Step 4: MAF + Hashed (Security Layer)                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Añadir Hashed como capa de seguridad sobre las tools              ║
║    • Identidad criptográfica del agente (PEM)                               ║
║    • Políticas: qué tools puede usar, cuáles están bloqueadas               ║
║    • Guards: cada tool pasa por Hashed antes de ejecutarse                  ║
║    • Audit trail: todo queda registrado (hashed logs list)                  ║
║                                                                              ║
║  ARQUITECTURA:                                                               ║
║                                                                              ║
║    LLM decide llamar tool                                                    ║
║        ↓                                                                     ║
║    MAF invoca la función Python                                               ║
║        ↓                                                                     ║
║    Hashed guard intercepta                                                   ║
║        ↓                           ↓                                         ║
║    Policy: ALLOW              Policy: DENY                                   ║
║        ↓                           ↓                                         ║
║    Tool ejecuta → resultado    Bloquea → log audit                           ║
║        ↓                           ↓                                         ║
║    Retorna al LLM             Retorna "Action denied"                        ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step4_hashed.py                                                    ║
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

# Directorio de secrets — se crea automáticamente si no existe
SECRETS_DIR = os.path.join(os.path.dirname(__file__), "secrets")
PEM_PATH = os.path.join(SECRETS_DIR, "lab01_agent.pem")


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZACIÓN DE HASHED
# ══════════════════════════════════════════════════════════════════════════════

async def init_hashed() -> HashedCore:
    """
    Crea e inicializa la identidad Hashed del agente.

    IDENTIDAD CRIPTOGRÁFICA:
      - Primera vez: genera un par de claves (privada → PEM, pública → backend)
      - Siguientes veces: carga el PEM existente → misma identidad
      - El PEM = el "pasaporte" del agente. Mismo PEM = mismo agente en Hashed.

    NO hardcodear el password en código — leerlo del .env.
    """
    os.makedirs(SECRETS_DIR, exist_ok=True)

    password = os.getenv("HASHED_IDENTITY_PASSWORD", "changeme")

    # load_or_create_identity:
    #   - Si el PEM existe → lo carga con el password
    #   - Si no existe    → genera un nuevo par de claves y guarda el PEM
    identity = load_or_create_identity(PEM_PATH, password)

    config = HashedConfig()  # Lee HASHED_BACKEND_URL y HASHED_API_KEY del .env

    core = HashedCore(
        config=config,
        identity=identity,
        agent_name="Lab01 MAF Agent",    # Nombre visible en el dashboard Hashed
        agent_type="educational",          # Tipo de agente (para categorización)
    )

    await core.initialize()  # Registra el agente en el backend Hashed
    print(f"🔐 Hashed: agente '{core.agent_name}' inicializado")
    print(f"   Public key: {identity.public_key_hex[:16]}...")

    return core


# ══════════════════════════════════════════════════════════════════════════════
# POLÍTICAS
# ══════════════════════════════════════════════════════════════════════════════

async def configurar_politicas(core: HashedCore) -> None:
    """
    Define qué puede y qué NO puede hacer el agente.

    POLÍTICA = (nombre_tool, permitido, metadata)

    Las políticas se sincronizan con el backend Hashed y también
    se aplican localmente (sin conexión funciona igual).
    """
    politicas = [
        # Tools PERMITIDAS
        ("obtener_info_framework", True,  {"riesgo": "bajo",    "max_hora": 100}),
        ("comparar_frameworks",    True,  {"riesgo": "bajo",    "max_hora": 50}),
        ("listar_frameworks",      True,  {"riesgo": "bajo",    "max_hora": 200}),
        # Tools BLOQUEADAS (para demo del sistema de seguridad)
        ("borrar_datos",           False, {"riesgo": "critico", "razon": "irreversible"}),
        ("enviar_email",           False, {"riesgo": "alto",    "razon": "requiere_aprobacion_humana"}),
    ]

    for nombre, permitido, meta in politicas:
        core.policy_engine.add_policy(nombre, allowed=permitido, metadata=meta)
        estado = "✅ ALLOW" if permitido else "❌ DENY"
        print(f"   Política: {nombre:30} {estado}")

    # Sincronizar con el backend (no-fatal si falla)
    try:
        await core.push_policies_to_backend()
        print("   ✅ Políticas sincronizadas con el backend")
    except Exception as e:
        print(f"   ⚠️  Sync backend falló (políticas locales funcionan igual): {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS CON HASHED GUARDS
# ══════════════════════════════════════════════════════════════════════════════
#
# PATRÓN:
#   1. Definir la función interna (_impl)
#   2. Envolver con core.guard(nombre_tool) → crea la versión "guardada"
#   3. Pasar la versión guardada al Agent como tool
#
# El guard:
#   - Consulta la política (allow/deny)
#   - Si allow → ejecuta la función
#   - Si deny  → lanza PolicyViolationError (no ejecuta la función)
#   - En ambos casos → registra en el audit trail


def crear_tools_con_guards(core: HashedCore):
    """
    Crea las tools de este lab con guards de Hashed.

    Retorna un dict {nombre: función_guardada} para usar en el Agent.
    """

    # ── Tool 1: Obtener info de framework ────────────────────────────────────

    async def _obtener_info_framework_impl(nombre: str) -> str:
        """Implementación interna — sin guard."""
        frameworks = {
            "maf":         "Microsoft Agent Framework — SDK oficial de Microsoft para agentes AI.",
            "langchain":   "LangChain — framework popular para aplicaciones con LLMs y RAG.",
            "crewai":      "CrewAI — orquestación de múltiples agentes con roles definidos.",
            "strands":     "Strands — framework de AWS para agentes con Amazon Bedrock.",
            "autogen":     "AutoGen — Microsoft Research, conversaciones entre agentes.",
            "semantic kernel": "Semantic Kernel — SDK enterprise multi-lenguaje de Microsoft.",
        }
        return frameworks.get(nombre.lower(), f"Framework '{nombre}' no encontrado.")

    # Aplicar el guard de Hashed
    _obtener_info_guarded = core.guard("obtener_info_framework")(_obtener_info_framework_impl)

    def obtener_info_framework(
        nombre: Annotated[str, Field(description="Nombre del framework: maf, langchain, crewai, strands, autogen, 'semantic kernel'")],
    ) -> str:
        """
        Obtiene información sobre un framework de agentes AI.
        Usa cuando el usuario pregunte por un framework específico.
        """
        try:
            return asyncio.get_event_loop().run_until_complete(_obtener_info_guarded(nombre))
        except Exception as e:
            return f"⛔ Acción bloqueada por política de seguridad: {e}"

    # ── Tool 2: Comparar frameworks ──────────────────────────────────────────

    async def _comparar_impl(framework_a: str, framework_b: str) -> str:
        return f"Comparación {framework_a} vs {framework_b}: ambos son buenos, depende del caso de uso."

    _comparar_guarded = core.guard("comparar_frameworks")(_comparar_impl)

    def comparar_frameworks(
        framework_a: Annotated[str, Field(description="Primer framework")],
        framework_b: Annotated[str, Field(description="Segundo framework")],
    ) -> str:
        """
        Compara dos frameworks de agentes AI.
        Usa cuando el usuario quiera comparar dos opciones.
        """
        try:
            return asyncio.get_event_loop().run_until_complete(_comparar_guarded(framework_a, framework_b))
        except Exception as e:
            return f"⛔ Acción bloqueada por política de seguridad: {e}"

    # ── Tool 3: Borrar datos — BLOQUEADA por política ────────────────────────
    #
    # Esta tool existe para DEMOSTRAR que el sistema de seguridad funciona.
    # La política "borrar_datos" está en DENY → el guard la bloqueará.

    async def _borrar_datos_impl(target: str) -> str:
        # Este código NUNCA se ejecuta porque el guard bloquea antes
        return f"Datos borrados: {target}"

    _borrar_datos_guarded = core.guard("borrar_datos")(_borrar_datos_impl)

    def borrar_datos(
        target: Annotated[str, Field(description="Qué datos borrar")],
    ) -> str:
        """
        Borra datos del sistema.
        NOTA: Esta acción está bloqueada por política de seguridad.
        """
        try:
            return asyncio.get_event_loop().run_until_complete(_borrar_datos_guarded(target))
        except Exception as e:
            return f"⛔ Acción bloqueada por política de seguridad Hashed: {e}"

    return [obtener_info_framework, comparar_frameworks, borrar_datos]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("  Lab 01 — Step 4: MAF + Hashed Security")
    print("=" * 60)

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    api_key  = os.getenv("AZURE_AI_AGENTS_KEY")

    if not endpoint or not api_key:
        print("❌ Falta FOUNDRY_PROJECT_ENDPOINT o AZURE_AI_AGENTS_KEY en .env")
        return

    if not os.getenv("HASHED_API_KEY"):
        print("❌ Falta HASHED_API_KEY en .env")
        return

    # ── 1. Inicializar Hashed ─────────────────────────────────────────────────
    print("\n🔐 Inicializando Hashed...")
    core = await init_hashed()

    # ── 2. Configurar políticas ───────────────────────────────────────────────
    print("\n📋 Configurando políticas de seguridad:")
    await configurar_politicas(core)

    # ── 3. Crear tools con guards ─────────────────────────────────────────────
    tools_con_guards = crear_tools_con_guards(core)
    print(f"\n🛠️  {len(tools_con_guards)} tools registradas con guards Hashed")

    # ── 4. Crear el agente MAF ────────────────────────────────────────────────
    async with AIProjectClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    ) as project_client:

        maf_client = FoundryChatClient(project_client=project_client)

        agent = Agent(
            client=maf_client,
            name="AgenteSeguro",
            instructions="""Eres un asistente educativo sobre frameworks de agentes AI.
            
Tienes tools disponibles. SIEMPRE úsalas para responder.
Si una tool retorna "⛔ Acción bloqueada", informa al usuario que la acción fue denegada por el sistema de seguridad.
Responde en español.""",
            tools=tools_con_guards,
        )

        print("\n✅ Agente MAF + Hashed listo")
        print()

        session = agent.create_session()

        # ── Conversación de demo ──────────────────────────────────────────────

        conversacion = [
            "¿Qué sabes sobre MAF?",
            "Compara LangChain con CrewAI.",
            "Borra todos los datos del sistema.",   # ← SERÁ BLOQUEADA por Hashed
            "¿Qué pasó con el intento de borrar datos?",
        ]

        for i, mensaje in enumerate(conversacion, 1):
            print(f"📨 [{i}/{len(conversacion)}] Usuario: {mensaje}")
            respuesta = await agent.run(mensaje, session=session)
            print(f"🤖 Agente: {respuesta}")
            print()

    # ── 5. Mostrar audit trail ────────────────────────────────────────────────
    print("─" * 60)
    print("  📊 AUDIT TRAIL — Para ver el log completo:")
    print()
    print("  $ hashed logs list")
    print()
    print("  Deberías ver:")
    print("    ✓ obtener_info_framework → success")
    print("    ✓ comparar_frameworks    → success")
    print("    ✗ borrar_datos           → denied   ← BLOQUEADO")
    print()

    # ── 6. Shutdown limpio ────────────────────────────────────────────────────
    await core.shutdown()

    print("=" * 60)
    print("  ✅ Step 4 completado — Lab 01 terminado")
    print()
    print("  Conceptos aprendidos:")
    print("    • load_or_create_identity() → PEM = identidad del agente")
    print("    • HashedCore → motor de seguridad")
    print("    • core.policy_engine.add_policy() → políticas allow/deny")
    print("    • core.guard(nombre)(fn) → wrapper de seguridad")
    print("    • Audit trail automático → hashed logs list")
    print()
    print("  Todo funciona junto:")
    print("    MAF → maneja el loop de agente")
    print("    Foundry → provee el LLM")
    print("    Hashed → seguridad, identidad y auditoría")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
