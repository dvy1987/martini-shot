"""Grafana-as-code for Run Pulse (C-4.5) — files exist and are provisionable."""

from pathlib import Path

from scripts.provision_grafana import load_dashboards, provision

ROOT = Path(__file__).resolve().parents[1]


def test_dashboards_load_with_run_pulse_uids() -> None:
    rows = load_dashboards()
    uids = {row["uid"] for row in rows}
    assert uids == {"pc-station-health", "pc-finishing-cost", "pc-interventions"}


def test_dry_run_does_not_claim_applied() -> None:
    result = provision(load_dashboards(), yes=False)
    assert result["applied"] is False
    assert "pc-interventions" in result["uids"]


def test_alert_rule_file_present() -> None:
    path = ROOT / "infra" / "grafana" / "alerts" / "run-pulse.yaml"
    text = path.read_text(encoding="utf-8")
    assert "pc-spend-80" in text
    assert "pc-station-fail-rate" in text
