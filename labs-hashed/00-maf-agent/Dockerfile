# ─────────────────────────────────────────────────────────────────
# Dockerfile — MAF Research Agent (Streamlit UI)
#
# Deploy to Azure Container Apps (GA — no Docker local needed):
#   az containerapp up --name maf-research-agent \
#     --resource-group <your-resource-group> --source .
#
# Run locally (if Docker is installed):
#   docker build -t maf-research-agent .
#   docker run -p 8080:8080 --env-file .env maf-research-agent
# ─────────────────────────────────────────────────────────────────

FROM python:3.11-slim

LABEL maintainer="AI Agent Course"
LABEL description="MAF Research Agent — Azure AI Agents + Hashed SDK"
LABEL version="2.0.0"

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY agent.py .
COPY agent_core.py .
COPY tools.py .
COPY app.py .

# Runtime directory for Hashed identity keys
RUN mkdir -p /app/secrets

# Environment variable defaults
# (override with --env-vars in az containerapp up)
ENV AZURE_OPENAI_DEPLOYMENT_NAME=DeepSeek-V3-0324
ENV AZURE_OPENAI_API_VERSION=2025-01-01-preview
ENV HASHED_IDENTITY_PASSWORD=changeme_in_production

# Streamlit listens on 8080 (Azure Container Apps default ingress)
EXPOSE 8080

# Health check — Streamlit serves HTML on /
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Start Streamlit — binds to 0.0.0.0 so Azure can reach it
CMD ["streamlit", "run", "app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
