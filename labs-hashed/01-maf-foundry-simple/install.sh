#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Lab 01 — MAF + Foundry Simple — Script de instalación
# ══════════════════════════════════════════════════════════════════════════════
#
# PRE-REQUISITOS:
#   Python 3.10+  (MAF requiere >=3.10. macOS tiene 3.9 por defecto → usa brew/pyenv)
#   az login      (azure-ai-projects y azure-ai-agents >= 1.1 usan OAuth, no API key)
#
# CÓMO USAR:
#   cd labs-hashed/01-maf-foundry-simple
#   /opt/homebrew/bin/python3.13 -m venv venv   # macOS con Homebrew
#   source venv/bin/activate
#   chmod +x install.sh && ./install.sh

set -e

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Lab 01 — Instalando dependencias"
echo "═══════════════════════════════════════════════════"
echo ""

echo "📦 Actualizando pip..."
pip install --upgrade pip --quiet

echo ""
echo "📦 Paso 1/2: Instalando paquetes de Azure + Hashed..."
pip install -r requirements.txt

echo ""
echo "📦 Paso 2/2: Instalando MAF (pre-release)..."
echo "   (agent-framework no está en el índice estable de PyPI)"
pip install --pre -r requirements-maf.txt

echo ""
echo "✅ Verificando instalación..."
python -c "import azure.ai.projects; print('  azure-ai-projects ✓')"
python -c "import agent_framework; print('  agent-framework   ✓')"
python -c "import hashed; print('  hashed-sdk        ✓')"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Todo instalado. Ahora configura el .env:"
echo "     cp .env.example .env"
echo ""
echo "  Luego corre en orden:"
echo "     python step1_local.py"
echo "     python step2_sessions.py"
echo "     python step3_tools.py"
echo "     python step4_hashed.py"
echo "═══════════════════════════════════════════════════"
echo ""
