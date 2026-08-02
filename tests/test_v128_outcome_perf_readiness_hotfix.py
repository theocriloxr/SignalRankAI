from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_version_and_release_fingerprint() -> None:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT

    assert APP_VERSION == "1.3.6.7"
    assert RELEASE_FINGERPRINT == "v1.3.6.7-integrity-accounting-dedup-hotfix-20260802"


def test_outcome_tracker_has_sql_func_and_separate_failure_boundaries() -> None:
    source = (ROOT / "engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert "from sqlalchemy import func, select" in source
    assert "signal_check_failed" in source
    assert "recipient_lookup_failed" in source
    assert "Error updating user performance for signal" not in source
    assert "SignalDelivery.sent_ok.is_(True)" in source
    assert "SignalDelivery.telegram_message_id.is_not(None)" in source
    assert "func.lower(SignalDelivery.delivery_state).in_(" in source


def test_railway_owns_prometheus_route_before_catch_all_mount() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    metrics_idx = source.index('@app.get("/metrics/prometheus"')
    mount_idx = source.index('app.mount("/", _web_app)')
    assert metrics_idx < mount_idx
    assert "prometheus_metrics_text()" in source[metrics_idx:mount_idx]


def test_readiness_requires_direct_railway_observability_routes() -> None:
    from scripts.production_readiness_check import run_readiness_checks

    result = run_readiness_checks(ROOT)
    checks = {item["name"]: item for item in result["checks"]}
    assert result["ok"] is True
    assert checks["railway_direct_observability_routes"]["ok"] is True


def test_current_environment_profiles_are_present() -> None:
    assert (ROOT / "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example").exists()
    assert (ROOT / "SignalRankAI_v1.3.2_Railway_Full_System_Live_Paystack_Staging.env.example").exists()
