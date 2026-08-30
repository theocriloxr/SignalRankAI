from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.mt5_bridge import MT5Bridge, MT5Order


def test_native_mt5_bridge_is_default_off(monkeypatch) -> None:
    monkeypatch.delenv("NATIVE_MT5_BRIDGE_ENABLED", raising=False)
    assert MT5Bridge._native_enabled() is False


def test_native_mt5_bridge_never_runs_on_railway(monkeypatch) -> None:
    monkeypatch.setenv("NATIVE_MT5_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project")
    assert MT5Bridge._native_enabled() is False


def test_long_and_short_order_direction_maps_correctly() -> None:
    long_order = MT5Order("EURUSD", 0.1, "long", 1.1, 1.0, 1.2)
    short_order = MT5Order("EURUSD", 0.1, "short", 1.1, 1.2, 1.0)
    assert long_order.to_mt5_type() == 0
    assert short_order.to_mt5_type() == 1


def test_native_position_size_uses_real_account_and_broker_spec() -> None:
    bridge = MT5Bridge()
    account = SimpleNamespace(equity=10_000.0)
    spec = SimpleNamespace(
        volume_min=0.1,
        volume_max=100.0,
        volume_step=0.1,
        trade_tick_size=0.01,
        trade_tick_value_loss=0.1,
        trade_tick_value=0.1,
        point=0.01,
    )
    size = bridge._calculate_volume(
        {
            "entry": 100.0,
            "stop_loss": 99.0,
            "risk_pct": 1.0,
        },
        symbol_info=spec,
        account_info=account,
    )
    assert size == 10.0


def test_native_position_size_never_falls_back_to_micro_lot() -> None:
    bridge = MT5Bridge()
    assert bridge._calculate_volume({}, symbol_info=object(), account_info=object()) == 0.0


@pytest.mark.asyncio
async def test_direct_native_execution_requires_gate_authorisation() -> None:
    bridge = MT5Bridge()
    ok, message, ticket = await bridge.execute_signal(
        {
            "signal_id": "sig",
            "asset": "EURUSD",
            "direction": "long",
            "entry": 1.1,
            "stop_loss": 1.0,
            "take_profit": 1.2,
        }
    )
    assert ok is False
    assert "ExecutionGate" in message
    assert ticket is None


def test_native_geometry_validation_is_direction_aware() -> None:
    assert MT5Bridge._validate_geometry("buy", 100, 95, 110)
    assert MT5Bridge._validate_geometry("sell", 100, 105, 90)
    assert not MT5Bridge._validate_geometry("buy", 100, 105, 110)
    assert not MT5Bridge._validate_geometry("sell", 100, 95, 90)
