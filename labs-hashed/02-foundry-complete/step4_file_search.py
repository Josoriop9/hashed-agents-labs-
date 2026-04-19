"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 02 — Step 4: File Search + Vector Stores (RAG automático)              ║
║  "Sube tus documentos y el agente los busca automáticamente"                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender File Search como RAG nativo de Foundry                  ║
║    • Vector Store — índice de documentos en Azure                            ║
║    • File Upload — subir archivos al proyecto                               ║
║    • FileSearchTool — habilitar RAG automático en el agente                  ║
║                                                                              ║
║  RAG MANUAL vs FILE SEARCH NATIVO:                                           ║
║    Manual: tu código chunka → embeddings → vector DB → retrieval            ║
║    File Search: subes archivos → Foundry hace TODO automáticamente           ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step4_file_search.py                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os
import io

from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.agents.models import (
    FileSearchTool,
    VectorStoreDataSource,
    VectorStoreDataSourceAssetType,
    RunStatus,
)
from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# ¿QUÉ ES FILE SEARCH EN FOUNDRY?
# ══════════════════════════════════════════════════════════════════════════════
#
#  File Search = RAG (Retrieval Augmented Generation) automático.
#
#  FLUJO SIMPLIFICADO:
#    1. Subes documentos (PDF, TXT, DOCX...) a Foundry
#    2. Foundry los procesa: chunking + embeddings + Vector Store
#    3. El agente tiene FileSearchTool activado
#    4. Cuando el usuario pregunta → el agente busca en el Vector Store
#    5. Los fragmentos relevantes se pasan como contexto al LLM
#
#  COMPONENTES:
#    File       → el documento que subes (PDF, TXT, DOCX, etc.)
#    VectorStore → índice vectorial donde se guardan los embeddings
#    FileSearchTool → habilita la búsqueda en el Vector Store
#
#  VENTAJA vs RAG manual:
#    ✓ No necesitas código de chunking, embedding, ni vector DB
#    ✓ Foundry gestiona todo (incluyendo actualización de docs)
#    ✓ Escala automáticamente


# ── Documentos de demo (la "base de conocimiento" de la startup) ──────────────

DOCS_DEMO = {
    "producto.txt": """
TechStartup Inc — Guía del Producto v3.0

DESCRIPCIÓN DEL PRODUCTO:
TechStartup Inc ofrece una plataforma de AI Agents que permite a las empresas 
desplegar agentes inteligentes sin escribir código. La plataforma incluye:
- AgentBuilder: drag-and-drop para crear workflows de agentes
- AgentMonitor: dashboard de métricas y logs en tiempo real  
- AgentMarket: marketplace de templates de agentes

PLANES DISPONIBLES:
- Starter: hasta 3 agentes, 1,000 runs/mes — $49/mes
- Growth: hasta 20 agentes, 10,000 runs/mes — $199/mes  
- Enterprise: agentes ilimitados, runs ilimitados — precio personalizado

INTEGRACIONES DISPONIBLES:
Slack, Microsoft Teams, Salesforce, HubSpot, Jira, GitHub, Zapier
""",

    "soporte.txt": """
TechStartup Inc — Política de Soporte

NIVELES DE SOPORTE:
1. Community (gratuito): foro de la comunidad, tiempo de respuesta 48-72h
2. Standard (Starter/Growth): email support, tiempo de respuesta 24h
3. Premium (Enterprise): Slack dedicado + llamadas, tiempo de respuesta 4h
4. White Glove: Customer Success Manager dedicado, tiempo de respuesta 1h

HORARIO:
Community y Standard: L-V 9am-6pm EST
Premium: L-V 8am-8pm EST  
White Glove: 24/7

CÓMO CONTACTAR:
- Portal: support.techstartup.io
- Email: support@techstartup.io
- Para Enterprise: canal Slack dedicado #support-<nombre-empresa>
""",

    "faq.txt": """
TechStartup Inc — Preguntas Frecuentes

P: ¿Cuánto tiempo tarda en configurar un agente?
R: Con AgentBuilder, menos de 10 minutos. Sin código necesario.

P: ¿Mis datos están seguros?
R: Sí. TechStartup es SOC2 Type II y cumple GDPR y CCPA. Los datos se 
   encriptan en tránsito y en reposo. Nunca se usan para entrenar modelos.

P: ¿Puedo integrar mis propias LLMs?
R: Sí. Soportamos OpenAI, Azure OpenAI, Anthropic, Google Gemini y modelos 
   propios vía API compatible con OpenAI.

P: ¿Qué pasa si supero el límite de runs?
R: Los runs adicionales se cobran a $0.002/run. Puedes configurar alertas
   y límites desde el panel de administración.

P: ¿Tienen API?
R: Sí. API REST documentada en docs.techstartup.io/api. 
   También hay SDK para Python, JavaScript y Go.
""",
}


async def subir_documentos(project_client: AIProjectClient) -> list[str]:
    """
    Sube documentos al proyecto de Foundry.
    Retorna lista de file_ids.
    """
    print("\n  📄 Subiendo documentos al proyecto de Foundry...")
    file_ids = []
    agents_client = project_client.agents

    for nombre, contenido in DOCS_DEMO.items():
        # Crear un file-like object en memoria
        archivo = io.BytesIO(contenido.encode("utf-8"))
        archivo.name = nombre  # Foundry usa el .name para el content-type

        # Subir el archivo
        file_obj = await agents_client.upload_file(
            file=archivo,
            purpose="assistants",  # "assistants" = para ser usado por agentes
        )
        file_ids.append(file_obj.id)
        print(f"  ✅ Subido: {nombre} → id: {file_obj.id[:25]}...")

    return file_ids


async def crear_vector_store(
    project_client: AIProjectClient,
    file_ids: list[str]
) -> str:
    """
    Crea un Vector Store con los archivos subidos.

    Vector Store = la base de datos vectorial donde viven los embeddings.
    Foundry hace el chunking y embedding automáticamente.
    """
    print("\n  🗄️  Creando Vector Store (Foundry hace chunking + embeddings)...")
    agents_client = project_client.agents

    vector_store = await agents_client.create_vector_store(
        name="TechStartup-KnowledgeBase",
        file_ids=file_ids,
    )
    print(f"  ✅ Vector Store creado: {vector_store.id[:25]}...")
    print(f"     Foundry está procesando los documentos (chunking + embeddings)...")

    # Esperar a que Foundry termine de procesar
    from azure.ai.agents.models import VectorStoreStatus
    max_wait = 60
    elapsed = 0
    while vector_store.status not in (VectorStoreStatus.COMPLETED, "completed"):
        await asyncio.sleep(3)
        elapsed += 3
        vector_store = await agents_client.get_vector_store(vector_store.id)
        print(f"     Procesando... ({elapsed}s)")
        if elapsed >= max_wait:
            print("     ⚠️  Timeout esperando Vector Store. Continuando...")
            break

    print(f"  ✅ Vector Store listo: {vector_store.status}")
    return vector_store.id


async def demo_file_search(project_client: AIProjectClient) -> None:
    """
    Crea un agente con File Search y demuestra RAG automático.
    """
    agents_client = project_client.agents
    model = os.getenv("FOUNDRY_MODEL", "gpt-4o")

    # ── 1. Subir documentos ───────────────────────────────────────────────────
    file_ids = await subir_documentos(project_client)

    # ── 2. Crear Vector Store ─────────────────────────────────────────────────
    vector_store_id = await crear_vector_store(project_client, file_ids)

    # ── 3. Crear agente CON FileSearchTool ───────────────────────────────────
    #
    # FileSearchTool recibe el vector_store_id.
    # El agente usará este Vector Store cuando reciba preguntas.
    # Foundry automáticamente busca los fragmentos más relevantes y los
    # incluye en el contexto del LLM.

    file_search_tool = FileSearchTool(vector_store_ids=[vector_store_id])

    print("\n  🤖 Creando agente con File Search (RAG automático)...")
    agent = await agents_client.create_agent(
        model=model,
        name="ConciergeAgent-FileSearch",
        instructions="""Eres el AI Concierge de TechStartup Inc.
        
Tienes acceso a la documentación oficial del producto en tu knowledge base.
SIEMPRE busca en la documentación para responder preguntas sobre:
- El producto (features, planes, precios)
- Soporte (niveles, horarios, contacto)
- FAQ (preguntas frecuentes)

Si no encuentras la información en la documentación, dilo claramente.
Responde en español. Sé conciso y cita la fuente cuando sea relevante.""",
        tools=file_search_tool.definitions,
        tool_resources=file_search_tool.resources,  # Conecta el Vector Store al agente
    )
    print(f"  ✅ Agente creado con RAG: {agent.id[:25]}...")

    # ── 4. Demo de conversación con RAG ───────────────────────────────────────
    print("\n  💬 Demo: Conversación con RAG automático")
    print("  (el agente busca en los documentos para responder)")
    print()

    preguntas = [
        "¿Qué planes tienen disponibles y cuánto cuestan?",
        "¿Cómo contacto soporte si soy cliente Enterprise?",
        "¿Los datos de mis usuarios están seguros con TechStartup?",
        "¿Puedo usar Google Gemini con su plataforma?",
    ]

    thread = await agents_client.create_thread()

    for i, pregunta in enumerate(preguntas, 1):
        print(f"  👤 [{i}/{len(preguntas)}] {pregunta}")

        await agents_client.create_message(
            thread_id=thread.id,
            role="user",
            content=pregunta,
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
                            respuesta = block.text.value
                            # Truncar para display
                            if len(respuesta) > 300:
                                respuesta = respuesta[:297] + "..."
                            print(f"  🤖 {respuesta}")
                    break
        else:
            print(f"  ❌ Run falló: {run.status}")

        print()

    # ── 5. Cleanup ────────────────────────────────────────────────────────────
    await agents_client.delete_agent(agent.id)
    # Opcional: borrar vector store y archivos para no acumular costos
    await agents_client.delete_vector_store(vector_store_id)
    for fid in file_ids:
        await agents_client.delete_file(fid)
    print("  🗑️  Agente, Vector Store y archivos eliminados")


async def main():
    print("=" * 60)
    print("  Lab 02 — Step 4: File Search + Vector Stores")
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
        await demo_file_search(project_client)

    print("=" * 60)
    print("  ✅ Step 4 completado")
    print()
    print("  Conceptos aprendidos:")
    print("    • File Upload → subir docs a Foundry")
    print("    • Vector Store → índice vectorial gestionado por Foundry")
    print("    • FileSearchTool → RAG automático sin código de retrieval")
    print("    • Foundry hace: chunking + embeddings + búsqueda vectorial")
    print()
    print("  Siguiente: python step5_mcp_tools.py")
    print("   → conectar servidores MCP como tools del agente")
