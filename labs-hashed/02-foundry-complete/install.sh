#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Lab 02 — Foundry Complete — Script de instalación
# ══════════════════════════════════════════════════════════════════════════════
#
# PRE-REQUISITOS:
#   Python 3.10+  (MAF requiere >=3.10. macOS tiene 3.9 por defecto → usa brew/pyenv)
#   az login      (azure-ai-projects y azure-ai-agents >= 1.1 usan OAuth, no API key)
#
# CÓMO USAR:
#   cd labs-hashed/02-foundry-complete
#   /opt/homebrew/bin/python3.13 -m venv venv   # macOS con Homebrew
#   source venv/bin/activate
#   chmod +x install.sh && ./install.sh

set -e

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Lab 02 — Instalando dependencias"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Paso 1: Actualizar pip ────────────────────────────────────────────────────
echo "📦 Actualizando pip..."
pip install --upgrade pip --quiet

# ── Paso 2: Paquetes de Azure AI Foundry + utilidades ─────────────────────────
echo ""
echo "📦 Paso 1/2: Instalando paquetes de Azure + Hashed..."
pip install -r requirements.txt

# ── Paso 3: MAF (pre-release — necesita --pre) ───────────────────────────────
echo ""
echo "📦 Paso 2/2: Instalando MAF (pre-release)..."
echo "   (agent-framework no está en el índice estable de PyPI)"
pip install --pre -r requirements-maf.txt

# ── Verificar instalación ─────────────────────────────────────────────────────
echo ""
echo "✅ Verificando instalación..."
python -c "import azure.ai.projects; print('  azure-ai-projects ✓')"
python -c "import azure.ai.agents; print('  azure-ai-agents   ✓')"
python -c "import agent_framework; print('  agent-framework   ✓')"
python -c "import hashed; print('  hashed-sdk        ✓')"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Todo instalado. Ahora configura el .env:"
echo "     cp .env.example .env"
echo "     # Edita .env con tus credenciales de Foundry"
echo ""
echo "  Luego corre:"
echo "     python step1_explore_foundry.py"
echo "═══════════════════════════════════════════════════"
echo ""
