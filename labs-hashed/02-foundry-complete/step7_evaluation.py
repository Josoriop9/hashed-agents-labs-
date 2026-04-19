"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Lab 02 — Step 7: Evaluaciones con Foundry Eval                             ║
║  "¿Qué tan bueno es mi agente? Midámoslo."                                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJETIVO: Entender Foundry Evaluation                                      ║
║    • Por qué evaluar es crítico (no basta con "parece correcto")            ║
║    • Evaluadores built-in: relevance, coherence, groundedness               ║
║    • Cómo crear un dataset de evaluación                                     ║
║    • Interpretar los resultados                                              ║
║                                                                              ║
║  CÓMO CORRER:                                                                ║
║    python step7_evaluation.py                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os
import json

from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# ¿POR QUÉ EVALUAR?
# ══════════════════════════════════════════════════════════════════════════════
#
#  El problema con "parece correcto":
#    - El LLM puede ser convincente pero incorrecto
#    - Un cambio de model o prompt puede degradar silenciosamente el agente
#    - No tienes métricas para comparar versiones del agente
#    - No sabes cuándo falla en producción
#
#  EVALUADORES BUILT-IN DE FOUNDRY:
#    • Relevance     → ¿La respuesta es relevante para la pregunta?
#    • Coherence     → ¿La respuesta es coherente y bien estructurada?
#    • Groundedness  → ¿La respuesta está basada en los documentos (RAG)?
#    • Fluency       → ¿La respuesta es fluida y natural?
#    • Similarity    → ¿Qué tan parecida es a la respuesta esperada?
#
#  CADA EVALUADOR USA UN "JUDGE" LLM:
#    Un LLM separado (usualmente GPT-4o) lee la pregunta + respuesta
#    y da un score del 1 al 5. Es "LLM-as-a-judge".


# ══════════════════════════════════════════════════════════════════════════════
# DATASET DE EVALUACIÓN
# ══════════════════════════════════════════════════════════════════════════════
#
# Un dataset de eval = lista de {query, response, ground_truth}
# - query: la pregunta del usuario
# - response: la respuesta del agente (generada o cargada)
# - ground_truth: la respuesta correcta esperada (para similarity)
# - context: los documentos que el agente tenía disponibles (para groundedness)

EVAL_DATASET = [
    {
        "query": "¿Cuánto cuesta el plan Growth?",
        "response": "El plan Growth de TechStartup cuesta $199 por mes e incluye hasta 20 agentes y 10,000 runs mensuales.",
        "ground_truth": "El plan Growth cuesta $199/mes, incluye hasta 20 agentes y 10,000 runs.",
        "context": "Planes: Starter $49 (3 agentes, 1K runs), Growth $199 (20 agentes, 10K runs), Enterprise personalizado.",
    },
    {
        "query": "¿Cuánto tiempo tarda en configurar un agente?",
        "response": "Con el AgentBuilder de TechStartup, puedes configurar un agente en menos de 10 minutos sin necesidad de escribir código.",
        "ground_truth": "Menos de 10 minutos con AgentBuilder. Sin código necesario.",
        "context": "FAQ: ¿Cuánto tiempo tarda? Con AgentBuilder, menos de 10 minutos. Sin código necesario.",
    },
    {
        "query": "¿Puedo usar Anthropic Claude con TechStartup?",
        "response": "Sí, TechStartup soporta Anthropic Claude, junto con OpenAI, Azure OpenAI, Google Gemini y modelos propios vía API compatible con OpenAI.",
        "ground_truth": "Sí, soportamos Anthropic, OpenAI, Azure OpenAI, Google Gemini y modelos propios.",
        "context": "FAQ: Soportamos OpenAI, Azure OpenAI, Anthropic, Google Gemini y modelos propios vía API compatible con OpenAI.",
    },
    {
        "query": "¿Tienen soporte en fines de semana?",
        "response": "El soporte en fines de semana depende del plan. El plan White Glove tiene soporte 24/7. Los otros planes tienen soporte de Lunes a Viernes.",
        "ground_truth": "Solo White Glove tiene soporte 24/7 (incluye fines de semana). Los demás planes son L-V.",
        "context": "Soporte: Community y Standard: L-V 9am-6pm. Premium: L-V 8am-8pm. White Glove: 24/7.",
    },
]


async def generar_respuestas_agente(project_client: AIProjectClient) -> list[dict]:
    """
    Genera respuestas del agente para el dataset de evaluación.

    En producción: guardarías estas respuestas en un archivo JSON
    para no re-generarlas en cada eval run.
    """
    print("\n  🤖 Generando respuestas del agente para el dataset...")

    maf_client = FoundryChatClient(project_client=project_client)
    agent = Agent(
        client=maf_client,
        name="EvalAgent",
        instructions="""Eres el AI Concierge de TechStartup Inc.
Responde preguntas sobre el producto basándote en la información disponible.
Responde en español. Sé conciso y preciso.""",
    )

    resultados = []
    for i, item in enumerate(EVAL_DATASET, 1):
        print(f"  [{i}/{len(EVAL_DATASET)}] {item['query'][:50]}...")
        respuesta = await agent.run(item["query"])
        resultados.append({
            "query": item["query"],
            "response": respuesta,
            "ground_truth": item["ground_truth"],
            "context": item["context"],
        })

    print(f"  ✅ {len(resultados)} respuestas generadas")
    return resultados


async def ejecutar_evaluacion(eval_data: list[dict]) -> None:
    """
    Ejecuta la evaluación con los evaluadores de Foundry.

    Usa azure-ai-evaluation que se conecta a un modelo judge.
    """
    print("\n  📊 Ejecutando evaluación...")

    # Configuración del modelo judge
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_KEY")
    judge_model = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    if not azure_endpoint or not azure_key:
        print("\n  ⚠️  AZURE_OPENAI_ENDPOINT y AZURE_OPENAI_KEY requeridos para evaluaciones")
        print("  El 'judge LLM' necesita un modelo separado (preferiblemente GPT-4o)")
        print()
        print("  Mientras tanto, mostramos cómo funciona conceptualmente:")
        mostrar_eval_conceptual(eval_data)
        return

    try:
        from azure.ai.evaluation import (
            evaluate,
            RelevanceEvaluator,
            CoherenceEvaluator,
            FluencyEvaluator,
            SimilarityEvaluator,
        )

        model_config = {
            "azure_endpoint": azure_endpoint,
            "api_key": azure_key,
            "azure_deployment": judge_model,
            "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        }

        # Guardar dataset como JSONL (formato requerido por evaluate())
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for item in eval_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
            dataset_path = f.name

        print(f"  Dataset: {len(eval_data)} ejemplos")
        print(f"  Evaluadores: Relevance, Coherence, Fluency, Similarity")
        print(f"  Judge model: {judge_model}")
        print()

        # Ejecutar la evaluación
        resultado = evaluate(
            data=dataset_path,
            evaluators={
                "relevance":  RelevanceEvaluator(model_config),
                "coherence":  CoherenceEvaluator(model_config),
                "fluency":    FluencyEvaluator(model_config),
                "similarity": SimilarityEvaluator(model_config),
            },
            evaluator_config={
                "relevance":  {"query": "${data.query}", "response": "${data.response}"},
                "coherence":  {"query": "${data.query}", "response": "${data.response}"},
                "fluency":    {"query": "${data.query}", "response": "${data.response}"},
                "similarity": {"response": "${data.response}", "ground_truth": "${data.ground_truth}"},
            },
        )

        # Mostrar resultados
        print("  ✅ Evaluación completada:")
        print()
        metrics = resultado.get("metrics", {})
        for metric, score in metrics.items():
            emoji = "🟢" if score >= 4.0 else ("🟡" if score >= 3.0 else "🔴")
            print(f"  {emoji} {metric:20} {score:.2f}/5.0")

        print()
        print("  Interpretación:")
        print("  🟢 ≥ 4.0 = Excelente  |  🟡 3.0-3.9 = Aceptable  |  🔴 < 3.0 = Necesita mejoras")

        # Cleanup
        import os as _os
        _os.unlink(dataset_path)

    except ImportError:
        print("  ⚠️  azure-ai-evaluation no instalado.")
        print("  pip install azure-ai-evaluation")
        mostrar_eval_conceptual(eval_data)
    except Exception as e:
        print(f"  ⚠️  Error en evaluación: {e}")
        mostrar_eval_conceptual(eval_data)


def mostrar_eval_conceptual(eval_data: list[dict]) -> None:
    """
    Muestra cómo se vería una evaluación sin correrla realmente.
    """
    print("\n  📊 DEMO CONCEPTUAL — Así se verían los resultados:")
    print()
    print(f"  Dataset: {len(eval_data)} preguntas evaluadas")
    print()
    print("  Métrica         | Score | Interpretación")
    print("  ─" * 40)
    print("  Relevance       | 4.5/5 | 🟢 Las respuestas son muy relevantes")
    print("  Coherence       | 4.2/5 | 🟢 Bien estructuradas y claras")
    print("  Fluency         | 4.8/5 | 🟢 Lenguaje natural y fluido")
    print("  Similarity      | 3.8/5 | 🟡 Similares pero con diferencias en detalle")
    print()
    print("  📋 Detalle por pregunta:")
    for i, item in enumerate(eval_data, 1):
        print(f"  [{i}] {item['query'][:45]}...")
        print(f"      Respuesta generada: {item['response'][:80]}...")
        print(f"      Respuesta esperada: {item['ground_truth'][:80]}")
        print()
    print("  Para ver resultados reales: configura AZURE_OPENAI_ENDPOINT en .env")


async def main():
    print("=" * 60)
    print("  Lab 02 — Step 7: Evaluaciones con Foundry Eval")
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
        # 1. Generar respuestas del agente
        eval_data = await generar_respuestas_agente(project_client)

    # 2. Ejecutar evaluación (fuera del AIProjectClient porque eval es sync)
    await ejecutar_evaluacion(eval_data)

    print("=" * 60)
    print("  ✅ Step 7 completado")
    print()
    print("  Conceptos aprendidos:")
    print("    • Eval = medir calidad del agente con métricas objetivas")
    print("    • LLM-as-a-judge: un modelo evalúa las respuestas de otro")
    print("    • Relevance, Coherence, Fluency, Similarity, Groundedness")
    print("    • Dataset de eval = baseline para comparar versiones")
    print()
    print("  Siguiente: python step8_full_startup.py")
    print("   → todo junto con Hashed para el agente final de la startup")
