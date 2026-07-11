from pathlib import Path

from scripts.production_readiness_check import run_readiness_checks


ROOT = Path(__file__).resolve().parents[1]


def test_offline_production_readiness_checks_pass():
    result = run_readiness_checks(ROOT)

    assert result["ok"] is True
    assert result["checked_count"] >= 7


def test_readiness_check_reports_named_checks():
    result = run_readiness_checks(ROOT)
    names = {check["name"] for check in result["checks"]}

    assert "governance_docs" in names
    assert "web_health_routes" in names
    assert "telemetry_markers" in names
    assert "telegram_core_commands" in names
