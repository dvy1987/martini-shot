# ─────────────────────────────────────────────────────────────────────────────
# Martini Shot Backend — Cloud Run Deployment Script (PowerShell)
# Provisions / updates the serverless FastAPI backend on Google Cloud Run.
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

$ProjectId = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { "martini-shot" }
$ServiceName = if ($env:SERVICE_NAME) { $env:SERVICE_NAME } else { "martini-shot-backend" }
$Region = if ($env:REGION) { $env:REGION } else { "us-central1" }
$EnvYaml = ".env.cloudrun.yaml"

Write-Host "=== Martini Shot Backend Deployment ===" -ForegroundColor Cyan
Write-Host "GCP Project:  $ProjectId"
Write-Host "Service Name: $ServiceName"
Write-Host "Region:       $Region"
Write-Host ""

try {
    # Generate YAML configuration from .env if present
    python -c @"
import yaml
from pathlib import Path

dotenv = Path('.env')
out = Path('$EnvYaml')

allowlist = [
    'GCP_PROJECT_ID', 'GCS_BUCKET', 'FIRESTORE_DATABASE', 'POST_COMMAND_API_KEY',
    'CORS_ALLOWED_ORIGINS', 'GRAFANA_STACK_URL', 'GRAFANA_OTLP_ENDPOINT',
    'GRAFANA_OTLP_TOKEN', 'GRAFANA_SA_TOKEN', 'MCP_MODE',
    'GOOGLE_GENAI_USE_ENTERPRISE', 'GOOGLE_CLOUD_LOCATION', 'GCS_SIGNING_SA',
    'GOOGLE_CLIENT_ID', 'GOOGLE_OWNER_EMAIL'
]

env_vars = {
    'GCP_PROJECT_ID': '$ProjectId',
    'POST_COMMAND_SERVICE_NAME': '$ServiceName',
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

if 'CORS_ALLOWED_ORIGINS' not in env_vars:
    env_vars['CORS_ALLOWED_ORIGINS'] = 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173'

# Always force the Linux binary path for Cloud Run deployment
env_vars['MCP_GRAFANA_BIN'] = '/usr/bin/mcp-grafana'

out.write_text(yaml.safe_dump(env_vars), encoding='utf-8')
print(f'Prepared {len(env_vars)} runtime configuration keys for Cloud Run.')
"@

    Write-Host "Submitting build and deploying to Cloud Run (min-instances=0)..." -ForegroundColor Yellow
    gcloud.cmd run deploy $ServiceName `
        --source . `
        --project $ProjectId `
        --region $Region `
        --platform managed `
        --allow-unauthenticated `
        --min-instances 0 `
        --max-instances 3 `
        --memory 2Gi `
        --cpu 1 `
        --timeout 300 `
        --port 8080 `
        --quiet `
        --env-vars-file $EnvYaml

    $ServiceUrl = (gcloud.cmd run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.url)").Trim()

    Write-Host ""
    Write-Host "=== Deployment Successful ===" -ForegroundColor Green
    Write-Host "Cloud Run URL: $ServiceUrl" -ForegroundColor Green
    Write-Host "Health Check:  $ServiceUrl/api/v1/health"
    Write-Host "API Version:   $ServiceUrl/api/v1/version"
    Write-Host ""
    Write-Host "Verifying health endpoint..."
    try {
        $health = Invoke-RestMethod -Uri "$ServiceUrl/api/v1/health" -Method Get -TimeoutSec 15
        Write-Host "Health check response: $($health | ConvertTo-Json -Compress)" -ForegroundColor Green
    } catch {
        Write-Warning "Initial health check attempt timed out or failed: $_"
    }
} finally {
    if (Test-Path $EnvYaml) {
        Remove-Item $EnvYaml -Force -ErrorAction SilentlyContinue
    }
}
