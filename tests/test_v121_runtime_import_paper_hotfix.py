from __future__ import annotations

import inspect
from pathlib import Path


def test_legacy_elliott_import_path_is_compatible():
    from engine.adaptive.elliott import ElliottWaveComponent as legacy
    from engine.adaptive.components.elliott import ElliottWaveComponent as canonical

    assert legacy is canonical


def test_db_session_accepts_deprecated_timeout_alias():
    from db.session import get_session

    signature = inspect.signature(get_session)
    assert "timeout_seconds" in signature.parameters
    assert "timeout" in signature.parameters


def test_launch_callsites_use_canonical_timeout_seconds():
    root = Path(__file__).resolve().parents[1]
    for relative in ("core/paper_trading_service.py", "signalrank_telegram/commands.py"):
        source = (root / relative).read_text(encoding="utf-8")
        assert "get_session(priority=" in source
        assert 'get_session(priority="background", label="paper.delivery_candidates", timeout=' not in source
        assert 'get_session(priority="interactive", label="about.metrics", timeout=' not in source


def test_staging_profile_keeps_dangerous_flags_off():
    root = Path(__file__).resolve().parents[1]
    profile = (root / "SignalRankAI_v1.2.1_Railway_Staging_Safe.env.example").read_text(encoding="utf-8")
    for line in (
        "REAL_EXECUTION_ENABLED=0",
        "AUTO_EXECUTION_ENABLED=0",
        "AUTO_TRADE_ENABLED=0",
        "COPY_TRADE_ENABLED=0",
        "REAL_PAYOUTS_ENABLED=0",
        "PAYMENTS_PUBLIC_ENABLED=0",
        "WS_INGEST_ENABLED=0",
        "PROXY_VALIDATION_ENABLED=0",
    ):
        assert line in profile


def test_railway_entrypoint_forces_live_risk_flags_off_before_config_imports():
    source = (Path(__file__).resolve().parents[1] / "railway_main.py").read_text(encoding="utf-8")
    assert "_enforce_nonproduction_safety_environment" in source
    for name in (
        "REAL_EXECUTION_ENABLED",
        "AUTO_EXECUTION_ENABLED",
        "AUTO_TRADE_ENABLED",
        "COPY_TRADE_ENABLED",
        "REAL_PAYOUTS_ENABLED",
        "PAYMENTS_PUBLIC_ENABLED",
        "FREE_SIGNAL_DISTRIBUTION_ENABLED",
        "FREE_RANDOM_DISTRIBUTION_ENABLED",
    ):
        assert f'"{name}"' in source
    assert source.index("_NONPRODUCTION_SAFETY_OVERRIDES") < source.index("from core.redis_state import state")
