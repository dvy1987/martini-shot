#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Martini Shot Backend — Cloud Run Deployment Script
# Provisions / updates the serverless FastAPI backend on Google Cloud Run.
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ID="${GCP_PROJECT_ID:-martini-shot}"
SERVICE_NAME="${SERVICE_NAME:-martini-shot-backend}"
REGION="${REGION:-us-central1}"
ENV_YAML=".env.cloudrun.yaml"

echo "=== Martini Shot Backend Deployment ==="
echo "GCP Project:  ${PROJECT_ID}"
echo "Service Name: ${SERVICE_NAME}"
echo "Region:       ${REGION}"
echo ""

# Ensure cleanup of temporary deployment files on exit
trap 'rm -f "${ENV_YAML}"' EXIT

# Generate sanitized runtime environment variables from .env if present
python -c "
import yaml
from pathlib import Path

dotenv = Path('.env')
out = Path('${ENV_YAML}')

allowlist = [
    'GCP_PROJECT_ID', 'GCS_BUCKET', 'FIRESTORE_DATABASE', 'POST_COMMAND_API_KEY',
    'CORS_ALLOWED_ORIGINS', 'GRAFANA_STACK_URL', 'GRAFANA_OTLP_ENDPOINT',
    'GRAFANA_OTLP_TOKEN', 'GRAFANA_SA_TOKEN', 'MCP_MODE',
    'GOOGLE_GENAI_USE_ENTERPRISE', 'GOOGLE_CLOUD_LOCATION', 'GCS_SIGNING_SA',
    'GOOGLE_CLIENT_ID', 'GOOGLE_OWNER_EMAIL'
]

env_vars = {
    'GCP_PROJECT_ID': '${PROJECT_ID}',
    'POST_COMMAND_SERVICE_NAME': '${SERVICE_NAME}',
}

if dotenv.exists():
    for line in dotenv.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {'\"', \"'\"}:
            v = v[1:-1]
        if k in allowlist and v:
            env_vars[k] = v

if 'GCP_PROJECT_ID' not in env_vars and 'GOOGLE_CLOUD_PROJECT' in env_vars:
    env_vars['GCP_PROJECT_ID'] = env_vars['GOOGLE_CLOUD_PROJECT']

# Ensure CORS includes wildcard or common frontend origins if not set
if 'CORS_ALLOWED_ORIGINS' not in env_vars:
    env_vars['CORS_ALLOWED_ORIGINS'] = 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173'

# Always force the Linux binary path for Cloud Run deployment
env_vars['MCP_GRAFANA_BIN'] = '/usr/bin/mcp-grafana'

out.write_text(yaml.safe_dump(env_vars), encoding='utf-8')
print(f'Prepared {len(env_vars)} runtime configuration keys for Cloud Run.')
"

echo "Submitting build and deploying to Cloud Run (min-instances=0)..."
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --memory 2Gi \
  --cpu 1 \
  --timeout 300 \
  --port 8080 \
  --quiet \
  --env-vars-file "${ENV_YAML}"

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format 'value(status.url)')

echo ""
echo "=== Deployment Successful ==="
echo "Cloud Run URL: ${SERVICE_URL}"
echo "Health Check:  ${SERVICE_URL}/api/v1/health"
echo "API Version:   ${SERVICE_URL}/api/v1/version"
echo ""
echo "Verifying health endpoint..."
curl -fsSL "${SERVICE_URL}/api/v1/health" || true
echo ""
