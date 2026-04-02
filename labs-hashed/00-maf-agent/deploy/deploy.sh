#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# deploy.sh — Deploy MAF Agent to Azure Container Apps
#
# PREREQUISITES:
#   1. Azure CLI: brew install azure-cli
#   2. Logged in: az login
#   3. NO Docker needed — Azure builds the image in the cloud 🎉
#
# USAGE:
#   chmod +x deploy/deploy.sh
#   ./deploy/deploy.sh          # run from maf-agent/ directory
#
# WHAT IT DOES:
#   1. Creates Container Apps Environment (first time only)
#   2. Runs az containerapp up → Azure builds image + deploys
#   3. Sets all env vars as secrets in Container Apps
#   4. Returns the public HTTPS URL
# ─────────────────────────────────────────────────────────────────

set -e

# ── Config ────────────────────────────────────────────────────────
# Override any of these via .env or environment variables:
#   AZURE_RESOURCE_GROUP=my-rg  ./deploy/deploy.sh
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-my-resource-group}"
LOCATION="${AZURE_LOCATION:-swedencentral}"
CONTAINER_APP_NAME="${AZURE_CONTAINER_APP_NAME:-maf-research-agent}"
ENVIRONMENT_NAME="${AZURE_ENVIRONMENT_NAME:-maf-agent-env}"
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"  # maf-agent/ directory

echo ""
echo "════════════════════════════════════════════════════"
echo "  🚀 MAF Research Agent → Azure Container Apps"
echo "════════════════════════════════════════════════════"
echo "  Resource Group  : $RESOURCE_GROUP"
echo "  Location        : $LOCATION"
echo "  App Name        : $CONTAINER_APP_NAME"
echo "  Source Dir      : $SOURCE_DIR"
echo "════════════════════════════════════════════════════"
echo ""

# ── Step 1: Load .env ─────────────────────────────────────────────
ENV_FILE="$SOURCE_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env not found at $ENV_FILE"
    echo "   Copy .env.example to .env and fill in values."
    exit 1
fi

# Load env vars
export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs)
echo "✅ Loaded .env"

# ── Step 2: Verify Azure login ────────────────────────────────────
echo ""
echo "🔐 Verifying Azure login..."
az account show --output none 2>/dev/null || {
    echo "   Not logged in. Running az login..."
    az login
}
echo "   ✅ Logged in as: $(az account show --query user.name -o tsv)"

# ── Step 3: Register Container Apps extension (if needed) ─────────
echo ""
echo "🔌 Ensuring az containerapp extension..."
az extension add --name containerapp --upgrade --only-show-errors 2>/dev/null || true
az provider register --namespace Microsoft.App --only-show-errors 2>/dev/null || true
az provider register --namespace Microsoft.OperationalInsights --only-show-errors 2>/dev/null || true
echo "   ✅ Extension ready"

# ── Step 4: Create Container Apps Environment (first time only) ───
echo ""
echo "🌍 Checking Container Apps Environment..."
EXISTING_ENV=$(az containerapp env list \
    --resource-group "$RESOURCE_GROUP" \
    --query "[?name=='$ENVIRONMENT_NAME'].name" \
    --output tsv 2>/dev/null || echo "")

if [ -z "$EXISTING_ENV" ]; then
    echo "   Creating environment: $ENVIRONMENT_NAME ..."
    az containerapp env create \
        --name "$ENVIRONMENT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output none
    echo "   ✅ Environment created"
else
    echo "   ✅ Environment already exists"
fi

# ── Step 5: Deploy with az containerapp up ─────────────────────────
echo ""
echo "🐳 Deploying to Azure Container Apps..."
echo "   (Azure builds the Docker image in the cloud — no local Docker needed)"
echo "   This takes ~5-10 minutes..."
echo ""

az containerapp up \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --environment "$ENVIRONMENT_NAME" \
    --source "$SOURCE_DIR" \
    --target-port 8080 \
    --ingress external \
    --env-vars \
        "AZURE_AI_AGENTS_ENDPOINT=$AZURE_AI_AGENTS_ENDPOINT" \
        "AZURE_AI_AGENTS_KEY=$AZURE_AI_AGENTS_KEY" \
        "AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME:-DeepSeek-V3-0324}" \
        "HASHED_BACKEND_URL=$HASHED_BACKEND_URL" \
        "HASHED_API_KEY=$HASHED_API_KEY" \
        "HASHED_IDENTITY_PASSWORD=$HASHED_IDENTITY_PASSWORD" \
        "HASHED_PEM_B64=secretref:hashed-pem-b64"

# ── Step 6: Get the URL ───────────────────────────────────────────
echo ""
APP_URL=$(az containerapp show \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" \
    --output tsv)

echo ""
echo "════════════════════════════════════════════════════"
echo "  ✅ DEPLOYED SUCCESSFULLY!"
echo "════════════════════════════════════════════════════"
echo ""
echo "  🌐 URL: https://$APP_URL"
echo ""
echo "  To view logs:"
echo "  az containerapp logs show --name $CONTAINER_APP_NAME \\"
echo "    --resource-group $RESOURCE_GROUP --follow"
echo ""
echo "  To update (redeploy):"
echo "  ./deploy.sh"
echo ""
echo "  To stop (save costs):"
echo "  az containerapp revision list --name $CONTAINER_APP_NAME \\"
echo "    --resource-group $RESOURCE_GROUP --output table"
echo "════════════════════════════════════════════════════"
