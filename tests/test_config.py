"""A-1 RED tests: core/config.py — env precedence and parsing (plan A-1 DoD, C-5.*)."""

from pathlib import Path

from backend.core.config import Settings, from_env, get_settings, reset_settings


def test_repr_redacts_secret_values() -> None:
    s = Settings(
        api_key="super-secret-api-key",  # pragma: allowlist secret
        grafana_sa_token="glsa_dummy_token",  # pragma: allowlist secret
        grafana_otlp_token="glc_dummy_token",  # pragma: allowlist secret
    )
    text = repr(s)
    assert "super-secret-api-key" not in text
    assert "glsa_dummy_token" not in text
    assert "glc_dummy_token" not in text
    assert "api_key=set" in text


def test_defaults_when_nothing_set() -> None:
    s = from_env(env={})
    assert isinstance(s, Settings)
    assert s.api_key == ""
    assert s.gcp_project_id == ""
    assert s.grafana_otlp_endpoint == ""
    assert s.cors_allowed_origins == []
    assert s.log_level == "INFO"
    assert s.service_name == "martini-shot-backend"


def test_gcp_project_alias_and_precedence() -> None:
    """GOOGLE_CLOUD_PROJECT is accepted as an alias; GCP_PROJECT_ID wins."""
    assert from_env(env={"GOOGLE_CLOUD_PROJECT": "alias-project"}).gcp_project_id == (
        "alias-project"
    )
    both = from_env(
        env={"GCP_PROJECT_ID": "primary", "GOOGLE_CLOUD_PROJECT": "alias-project"}
    )
    assert both.gcp_project_id == "primary"


def test_dotenv_values_applied(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        'POST_COMMAND_API_KEY="dotenv-key"\n'  # pragma: allowlist secret (dummy)
        "# comment line\n"
        "GCP_PROJECT_ID=dotenv-project\n"  # pragma: allowlist secret (dummy)
        "\n",
        encoding="utf-8",
    )
    s = from_env(env={}, dotenv=dotenv)
    assert s.api_key == "dotenv-key"  # pragma: allowlist secret (dummy)
    assert s.gcp_project_id == "dotenv-project"


def test_env_var_wins_over_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "POST_COMMAND_API_KEY=dotenv-key\n",  # pragma: allowlist secret (dummy)
        encoding="utf-8",
    )  # pragma: allowlist secret (dummy)
    s = from_env(env={"POST_COMMAND_API_KEY": "env-key"}, dotenv=dotenv)
    assert s.api_key == "env-key"  # pragma: allowlist secret (dummy)


def test_cors_origins_parsed_from_csv() -> None:
    s = from_env(env={"CORS_ALLOWED_ORIGINS": "http://a.test, http://b.test"})
    assert s.cors_allowed_origins == ["http://a.test", "http://b.test"]


def test_quoted_values_unquoted(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text('MCP_MODE="oss"\n', encoding="utf-8")
    s = from_env(env={}, dotenv=dotenv)
    assert s.mcp_mode == "oss"


def test_get_settings_is_cached_and_resettable(tmp_path: Path) -> None:
    reset_settings()
    first = get_settings(env={"POST_COMMAND_API_KEY": "one"})
    second = get_settings(env={"POST_COMMAND_API_KEY": "two"})
    assert first is second
    assert first.api_key == "one"  # pragma: allowlist secret (dummy)
    reset_settings()
    third = get_settings(env={"POST_COMMAND_API_KEY": "two"})
    assert third is not first
    assert third.api_key == "two"  # pragma: allowlist secret (dummy)
    reset_settings()
