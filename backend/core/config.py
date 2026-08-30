"""Application configuration (plan A-1).

Precedence: process environment > `.env` file > dataclass default.
Env var names match `.env.example`; secrets never live in code (C-5.1).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DOTENV = ".env"

_ENV_NAMES: dict[str, str] = {
    "gcp_project_id": "GCP_PROJECT_ID",
    "gcs_bucket": "GCS_BUCKET",
    "firestore_database": "FIRESTORE_DATABASE",
    "google_application_credentials": "GOOGLE_APPLICATION_CREDENTIALS",
    "grafana_stack_url": "GRAFANA_STACK_URL",
    "grafana_otlp_endpoint": "GRAFANA_OTLP_ENDPOINT",
    "grafana_otlp_token": "GRAFANA_OTLP_TOKEN",
    "mcp_mode": "MCP_MODE",
    "grafana_sa_token": "GRAFANA_SA_TOKEN",
    "api_key": "POST_COMMAND_API_KEY",  # pragma: allowlist secret (env var name, not a secret)
    "cors_allowed_origins": "CORS_ALLOWED_ORIGINS",
    "service_name": "POST_COMMAND_SERVICE_NAME",
    "log_level": "POST_COMMAND_LOG_LEVEL",
}


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings; defaults are safe (fail-closed)."""

    gcp_project_id: str = ""
    gcs_bucket: str = ""
    firestore_database: str = "(default)"
    google_application_credentials: str = ""
    grafana_stack_url: str = ""
    grafana_otlp_endpoint: str = ""
    grafana_otlp_token: str = ""
    mcp_mode: str = "hosted"
    grafana_sa_token: str = ""
    api_key: str = ""
    cors_allowed_origins: list[str] = field(default_factory=list)
    service_name: str = "martini-shot-backend"
    log_level: str = "INFO"


def parse_dotenv(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser: comments, blanks, surrounding quotes."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def from_env(env: Mapping[str, str], dotenv: Path | None = None) -> Settings:
    """Build Settings: dotenv first, then `env` mapping wins on conflicts."""
    merged: dict[str, str] = {}
    if dotenv is not None and dotenv.exists():
        merged.update(parse_dotenv(dotenv))
    merged.update(env)

    def pick(name: str) -> str:
        return merged.get(_ENV_NAMES[name], "").strip()

    cors = [o.strip() for o in pick("cors_allowed_origins").split(",") if o.strip()]
    return Settings(
        gcp_project_id=pick("gcp_project_id"),
        gcs_bucket=pick("gcs_bucket"),
        firestore_database=pick("firestore_database") or "(default)",
        google_application_credentials=pick("google_application_credentials"),
        grafana_stack_url=pick("grafana_stack_url"),
        grafana_otlp_endpoint=pick("grafana_otlp_endpoint"),
        grafana_otlp_token=pick("grafana_otlp_token"),
        mcp_mode=pick("mcp_mode") or "hosted",
        grafana_sa_token=pick("grafana_sa_token"),
        api_key=pick("api_key"),
        cors_allowed_origins=cors,
        service_name=pick("service_name") or "martini-shot-backend",
        log_level=(pick("log_level") or "INFO").upper(),
    )


_cached: Settings | None = None


def get_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Process-wide settings (cached); tests call reset_settings() between uses."""
    global _cached
    if _cached is None:
        source = dict(os.environ) if env is None else dict(env)
        _cached = from_env(source, dotenv=Path(ROOT_DOTENV))
    return _cached


def reset_settings() -> None:
    global _cached
    _cached = None
