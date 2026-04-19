"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 02 — Step 1: Explorar Azure AI Foundry                                 ║
║  "¿Qué tengo disponible en mi proyecto?"                                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender la infraestructura de Foundry                            ║
║    • Hub y Project — la organización de recursos                             ║
║    • Connections — links a servicios externos (Azure OpenAI, Bing...)        ║
║    • Model deployments — qué modelos están disponibles para usar             ║
║    • AI Services — los endpoints del proyecto                                ║
║                                                                              ║
║  CAPAS QUE USAMOS AQUÍ:                                                      ║
║    azure-ai-projects (AIProjectClient)  ← SDK para explorar el proyecto      ║
║    azure-ai-inference                   ← SDK para llamar modelos            ║
║                                                                              ║
║  ¿POR QUÉ NO MAF AQUÍ?                                                       ║
║    MAF es para orquestar agentes. Para explorar el proyecto (connections,    ║
║    models, datasets) usas directamente azure-ai-projects. MAF lo envuelve   ║
║    cuando creas el agente, no en la exploración.                             ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step1_explore_foundry.py                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os

from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

# rich: output bonito con tablas y colores
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()
    def section(title: str): console.print(Panel(f"[bold cyan]{title}[/bold cyan]"))
    def ok(msg: str):  console.print(f"  [green]✓[/green] {msg}")
    def info(msg: str): console.print(f"  [dim]{msg}[/dim]")
except ImportError:
    console = None
    def section(title: str): print(f"\n{'─'*60}\n  {title}\n{'─'*60}")
    def ok(msg: str):  print(f"  ✓ {msg}")
    def info(msg: str): print(f"    {msg}")

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# CONCEPTOS CLAVE DE FOUNDRY
# ══════════════════════════════════════════════════════════════════════════════
#
#  Hub → el workspace principal de Azure AI Foundry
#    - Es el contenedor de nivel más alto
#    - Administra networking, identidades, billing
#    - Una empresa típicamente tiene 1 Hub por entorno (dev/prod)
#
#  Project → tu proyecto de trabajo dentro del Hub
#    - Aquí viven los agentes, datasets, evaluaciones
#    - El endpoint que usas en el .env apunta a un Project
#    - Puedes tener múltiples proyectos por Hub
#
#  Connections → links a servicios externos
#    - Azure OpenAI connection → para usar modelos GPT/DeepSeek
#    - Bing connection → para búsqueda web (Grounding)
#    - Storage connection → para datos y datasets
#    - Cada tool del agente puede requerir una Connection
#
#  Model Deployments → el modelo listo para usar
#    - Tomas un modelo del catálogo (gpt-4o, DeepSeek-V3, Phi...)
#    - Lo "deployeas" → obtiene un nombre de deployment
#    - El deployment = el endpoint específico para ese modelo
#    - Puedes tener múltiples deployments del mismo modelo base


async def explorar_proyecto(client: AIProjectClient) -> None:
    """
    Explora la información básica del proyecto de Foundry.
    """
    section("1. INFORMACIÓN DEL PROYECTO")

    # El AIProjectClient tiene acceso a todo el proyecto
    # Cuando lo creas con un endpoint, sabe a qué Hub y Project apunta
    print(f"\n  Endpoint configurado: {os.getenv('FOUNDRY_PROJECT_ENDPOINT', 'N/A')[:60]}...")
    print(f"  Modelo configurado:   {os.getenv('FOUNDRY_MODEL', 'N/A')}")
    print()
    info("Este endpoint corresponde a:")
    info("  https://<account>.services.ai.azure.com/api/projects/<project>")
    info("  └─ services.ai.azure.com = Azure AI Foundry service")
    info("  └─ api/projects/<project> = tu proyecto específico")


async def explorar_connections(client: AIProjectClient) -> None:
    """
    Lista todas las connections del proyecto.

    CONNECTIONS = links a servicios externos que el proyecto puede usar.
    Cada tool de Foundry (Bing, Code Interpreter, etc.) necesita una connection.
    """
    section("2. CONNECTIONS DEL PROYECTO")
    print()
    info("Las Connections son los 'bridges' entre Foundry y servicios externos.")
    info("Cada tool avanzada necesita que exista la Connection correspondiente.")
    print()

    try:
        connections = []
        async for conn in client.connections.list():
            connections.append(conn)

        if not connections:
            info("No se encontraron connections en el proyecto.")
            info("Para agregar: ai.azure.com → Settings → Connections → + New connection")
        else:
            if console:
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Nombre", style="cyan")
                table.add_column("Tipo")
                table.add_column("Estado")
                for conn in connections:
                    table.add_row(
                        conn.name,
                        str(conn.connection_type),
                        "✓ Activa"
                    )
                console.print(table)
            else:
                for conn in connections:
                    ok(f"{conn.name} ({conn.connection_type})")

        print()
        info("Tipos de connections comunes:")
        info("  AzureOpenAI   → modelos GPT, embeddings")
        info("  BingSearch    → búsqueda web (Grounding)")
        info("  AzureBlob     → almacenamiento de archivos")
        info("  AzureSearch   → Azure Cognitive Search")
        info("  GitHub        → code repositories")

    except Exception as e:
        print(f"  ⚠️  Error al listar connections: {e}")
        info("Puede ser un problema de permisos o la feature no disponible.")


async def explorar_modelos(client: AIProjectClient) -> None:
    """
    Lista los modelos disponibles en el proyecto.

    MODELS en Foundry = dos conceptos separados:
    1. Model Catalog → catálogo completo (GPT-4o, Phi, DeepSeek, Llama, etc.)
    2. Deployments → los modelos que TÚ has deployeado y puedes usar
    """
    section("3. MODELOS DISPONIBLES")
    print()
    info("En Foundry hay dos tipos de modelos:")
    info("  a) Model Catalog → todos los modelos disponibles para deployear")
    info("  b) Deployments   → los que tú ya deployeaste y están listos para usar")
    print()

    # Intentar listar deployments a través de AI Inference
    try:
        from azure.ai.inference.aio import ChatCompletionsClient
        from azure.core.credentials import AzureKeyCredential as AKC

        # El endpoint de inference es la base del project endpoint
        project_ep = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
        # Extraer la base: https://<account>.services.ai.azure.com
        base_ep = project_ep.split("/api/projects")[0] if "/api/projects" in project_ep else project_ep
        api_key = os.getenv("AZURE_AI_AGENTS_KEY", "")

        info(f"Inference endpoint: {base_ep}")
        print()

        # Probar que el modelo configurado funciona
        model = os.getenv("FOUNDRY_MODEL", "")
        if model:
            ok(f"Modelo configurado en .env: {model}")
            info("  Para cambiar de modelo: cambia FOUNDRY_MODEL en .env")
            info("  y verifica que el deployment exista en ai.azure.com → Models + endpoints")

    except ImportError:
        info("azure-ai-inference no instalado. Run: pip install azure-ai-inference")

    print()
    info("Cómo ver modelos disponibles en tu proyecto:")
    info("  ai.azure.com → tu proyecto → Models + endpoints → Deployments")
    info()
    info("Cómo deployear un modelo nuevo:")
    info("  ai.azure.com → tu proyecto → Models + endpoints → + Deploy model")
    info("  → Model catalog → busca gpt-4o, Phi-3.5, DeepSeek, etc.")


async def explorar_agentes_existentes(client: AIProjectClient) -> None:
    """
    Lista los agentes que ya existen en el proyecto.

    IMPORTANTE: Los agentes en Foundry son PERSISTENTES.
    Cada vez que creas un agente, queda guardado en Azure con su agent_id.
    En producción, reutilizas el agent_id en lugar de crear uno nuevo cada vez.
    """
    section("4. AGENTES EXISTENTES EN FOUNDRY AGENT SERVICE")
    print()
    info("Los agentes en Foundry son PERSISTENTES — viven en Azure.")
    info("Cada agente tiene un agent_id único que no cambia entre deployments.")
    print()

    try:
        # Acceder al Agent Service a través de AIProjectClient
        agents_client = client.agents

        agents = []
        async for agent in agents_client.list_agents():
            agents.append(agent)

        if not agents:
            info("No hay agentes creados en este proyecto todavía.")
            info("Los crearemos en step2_agent_service.py")
        else:
            if console:
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Nombre", style="cyan")
                table.add_column("ID")
                table.add_column("Modelo")
                for a in agents:
                    table.add_row(
                        a.name or "(sin nombre)",
                        a.id[:20] + "...",
                        a.model or "N/A"
                    )
                console.print(table)
            else:
                for a in agents:
                    ok(f"{a.name} | id: {a.id[:20]}... | modelo: {a.model}")

    except Exception as e:
        print(f"  ⚠️  Error al listar agentes: {e}")
        info("Puede ser un problema de permisos o endpoint.")


async def main():
    if console:
        console.print(Panel(
            "[bold]Lab 02 — Step 1: Explorar Azure AI Foundry[/bold]\n"
            "[dim]¿Qué hay en mi proyecto?[/dim]",
            style="blue"
        ))
    else:
        print("=" * 60)
        print("  Lab 02 — Step 1: Explorar Azure AI Foundry")
        print("=" * 60)

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    api_key  = os.getenv("AZURE_AI_AGENTS_KEY")

    if not endpoint or not api_key:
        print("❌ Falta FOUNDRY_PROJECT_ENDPOINT o AZURE_AI_AGENTS_KEY en .env")
        return

    # ── AIProjectClient ───────────────────────────────────────────────────────
    #
    # Este es el cliente principal para EXPLORAR Foundry.
    # NO es para hacer inferencia (llamar al LLM) — eso lo hace MAF o InferenceClient.
    # SÍ es para: connections, model deployments, datasets, evaluations, agents.

    async with AIProjectClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    ) as client:
        await explorar_proyecto(client)
        await explorar_connections(client)
        await explorar_modelos(client)
        await explorar_agentes_existentes(client)

    # ── Resumen de la arquitectura ────────────────────────────────────────────
    section("RESUMEN: EL PUZZLE DE FOUNDRY")
    print()
    print("  Foundry tiene MÚLTIPLES SDKs, cada uno para una capa:")
    print()
    print("  azure-ai-projects   → explorar e interactuar con el proyecto")
    print("  azure-ai-agents     → crear agentes, threads, tools built-in")
    print("  azure-ai-inference  → llamar modelos directamente (sin agente)")
    print("  azure-ai-evaluation → evaluar calidad de respuestas")
    print("  agent-framework     → MAF: orquestación de alto nivel (todo junto)")
    print()
    print("  Siguiente: python step2_agent_service.py")
    print("   → crear tu primer agente persistente en Foundry con MAF")
    print()


if __name__ == "__main__":
    asyncio.run(main())
