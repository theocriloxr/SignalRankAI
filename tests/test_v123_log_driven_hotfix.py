from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_all_adaptive_component_compatibility_imports_exist() -> None:
    modules = [
        "elliott",
        "fibonacci",
        "harmonic",
        "ict_smc",
        "indicators",
        "order_flow",
        "price_action",
        "supply_demand",
        "wyckoff",
    ]
    for name in modules:
        module = importlib.import_module(f"engine.adaptive.{name}")
        assert module is not None


def test_full_system_ack_accepts_railway_quoted_value() -> None:
    from runtime_safety import FULL_SYSTEM_STAGING_TEST_ACK_VALUE, is_full_system_ack_valid

    assert is_full_system_ack_valid(FULL_SYSTEM_STAGING_TEST_ACK_VALUE)
    assert is_full_system_ack_valid(f'"{FULL_SYSTEM_STAGING_TEST_ACK_VALUE}"')
    assert is_full_system_ack_valid(f"  '{FULL_SYSTEM_STAGING_TEST_ACK_VALUE}'  ")
    assert not is_full_system_ack_valid("wrong")


def test_runtime_version_identifies_code_not_stale_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "1.2.0")
    import core.version as version

    version = importlib.reload(version)
    assert version.APP_VERSION == "1.2.5"
    assert version.CONFIGURED_APP_VERSION == "1.2.0"
    assert "v1.2.5-live-paystack-delivery-adaptive-telemetry-20260729" in version.get_version_banner()
    assert "configured_version=1.2.0" in version.get_version_banner()


def test_ultra_quality_reads_stop_loss_and_structured_targets() -> None:
    from engine.ultra_quality_filter import UltraQualityFilter

    quality_filter = UltraQualityFilter()
    signal = {
        "score": 96.0,
        "entry": 100.0,
        "stop_loss": 98.0,
        "targets": {"tp1": 105.0, "tp2": 108.0},
        "direction": "BUY",
        "regime": "TRENDING",
        "adx_trend": 32.0,
        "volume_ratio": 1.8,
        "volatility": 0.02,
        "session": "NEW_YORK",
        "confidence": 0.90,
        "atr": 1.0,
        "ema_50": 99.5,
        "trend_ema": 1.0,
        "trend_sma": 1.0,
        "rsi": 60.0,
        "macd_trend": 1.0,
        "nearest_support": 98.0,
        "nearest_resistance": 108.0,
        "htf_bias_aligned": True,
        "close_price": 100.0,
    }
    passed, reason, score = quality_filter.apply_ultra_filter(signal)
    assert passed is True
    assert reason.startswith("APPROVED")
    assert "R:R 0.00" not in reason
    assert "regime=UNKNOWN" not in reason
    assert score == 96.0


def test_signal_pipeline_orders_risk_and_context_before_ultra_gate() -> None:
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    stop_index = source.index("sig['stop_loss'] = sl")
    regime_index = source.index("sig['regime'] = str(regime", stop_index)
    ultra_index = source.index("if _env_bool('ULTRA_QUALITY_ENABLED'", stop_index)
    assert stop_index < ultra_index
    assert regime_index < ultra_index
    assert "regime = detect_market_regime(" in source
    assert "_regime_candles," in source


def test_paper_worker_handles_admission_deferrals_without_cycle_crash() -> None:
    source = (ROOT / "core" / "paper_trading_service.py").read_text(encoding="utf-8")
    assert "except NoncriticalWriteDropped" in source
    assert "paper_worker] delivery phase deferred" in source
    assert "paper_worker] mark phase deferred" in source
    assert "PAPER_WORKER_DB_PRIORITY" in source


def test_staging_profile_keeps_features_on_inside_sandbox() -> None:
    profile = (ROOT / "SignalRankAI_v1.2.4_Railway_Full_System_Staging_Test.env.example")
    assert profile.exists()
    text = profile.read_text(encoding="utf-8")
    for expected in (
        "FULL_SYSTEM_STAGING_TEST_MODE=1",
        "REAL_EXECUTION_ENABLED=1",
        "AUTO_TRADE_ENABLED=1",
        "COPY_TRADE_ENABLED=1",
        "PAYMENTS_PUBLIC_ENABLED=1",
        "REAL_PAYOUTS_ENABLED=1",
        "BYBIT_TESTNET=1",
        "MT5_ALLOW_LIVE_ACCOUNTS=0",
        "PROXY_VALIDATION_ENABLED=0",
        "PAPER_WORKER_DB_PRIORITY=interactive",
    ):
        assert expected in text
