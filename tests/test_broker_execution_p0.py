from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.env import SafetyFlags
from execution.service import ExecutionGate, ExecutionRequest


def _enabled_safety_flags() -> SafetyFlags:
    return SafetyFlags(
        auto_execution_enabled=True,
        auto_trade_enabled=True,
        copy_trade_enabled=True,
        payments_enabled=False,
        telegram_rich_messages_enabled=False,
        vip_webhook_dispatch_enabled=False,
        chat_mt5_credentials_enabled=False,
    )



def _integrity_signal(**overrides):
    from datetime import datetime, timezone
    payload = {
        "signal_id": "sig-7", "asset": "BTCUSDT", "asset_class": "crypto",
        "direction": "long", "timeframe": "1h", "entry": 100.0,
        "stop_loss": 95.0, "take_profit": [106.0, 110.0, 115.0],
        "strategy_name": "ema_trend", "score": 88.0,
        "quality_gate_passed": True, "ml_probability_calibrated": 0.67,
        "ml_calibration_version": "isotonic:test", "ml_calibration_validated": True,
        "ml_calibration_validation_rows": 250, "ml_calibration_brier": 0.16,
        "ml_calibration_ece": 0.04, "asset_discovery_provider": "metaapi",
        "generated_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return payload

def _allowed_request(**overrides) -> ExecutionRequest:
    values = {
        "user_id": 7,
        "signal_id": "sig-7",
        "signal": {
            "entry": 100.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "direction": "long",
        },
        "account_id": "account-7",
        "tier": "VIP",
        "mode": "auto",
        "user_enabled": True,
        "consent": True,
        "account_ready": True,
        "account_is_demo": True,
        "credentials_encrypted": True,
        "quote_trusted": True,
        "quote_age_seconds": 1.0,
        "max_quote_age_seconds": 15.0,
        "market_open": True,
        "risk_allowed": True,
        "evidence_allowed": True,
        "broker_healthy": True,
        "resources_available": True,
        "reconciliation_ready": True,
        "kill_switch": False,
    }
    values.update(overrides)
    return ExecutionRequest(**values)


@pytest.mark.asyncio
async def test_execution_gate_reserves_concurrent_request_atomically() -> None:
    gate = ExecutionGate(safety_flags=_enabled_safety_flags())
    calls = 0

    async def submit(_request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "order-7"

    first, second = await asyncio.gather(
        gate.execute(_allowed_request(), submit),
        gate.execute(_allowed_request(), submit),
    )

    assert calls == 1
    assert {first.status, second.status} <= {"SUBMITTING", "SUBMITTED"}
    final = await gate.execute(_allowed_request(), submit)
    assert final.status == "SUBMITTED"
    assert final.order_id == "order-7"
    assert calls == 1


def test_real_account_requires_separate_default_off_flag(monkeypatch) -> None:
    monkeypatch.delenv("REAL_EXECUTION_ENABLED", raising=False)
    gate = ExecutionGate(safety_flags=_enabled_safety_flags())

    decision = gate.preflight(_allowed_request(account_is_demo=False))

    assert decision.allowed is False
    assert "REAL_EXECUTION_DISABLED" in decision.reasons


def test_gate_blocks_stale_quote_and_unavailable_reconciliation() -> None:
    gate = ExecutionGate(safety_flags=_enabled_safety_flags())

    decision = gate.preflight(
        _allowed_request(
            quote_age_seconds=60.0,
            reconciliation_ready=False,
        )
    )

    assert decision.allowed is False
    assert "fresh_quote_required" in decision.reasons
    assert "reconciliation_unavailable" in decision.reasons


@pytest.mark.asyncio
async def test_metaapi_account_info_is_real_data_not_fake_balance(monkeypatch) -> None:
    import services.mt5_client as client

    async def fake_get(url, params=None):
        if url.endswith("/account-information"):
            return {
                "accountNumber": "123",
                "equity": "12500.50",
                "balance": "12000",
                "margin": "200",
                "freeMargin": "12300.50",
                "connectionStatus": "CONNECTED",
                "currency": "USD",
            }
        return {"server": "Broker-Demo", "state": "DEPLOYED"}

    monkeypatch.setattr(client, "_deploy_account", AsyncMock(return_value=None))
    monkeypatch.setattr(client, "_http_get", fake_get)

    info = await client.get_account_info("account-1")

    assert info is not None
    assert info["equity"] == 12500.5
    assert info["free_margin"] == 12300.5
    assert info["connected"] is True
    assert info["is_demo"] is True


@pytest.mark.asyncio
async def test_missing_or_stale_broker_quote_blocks_slippage(monkeypatch) -> None:
    import services.mt5_client as client

    stale = datetime.now(timezone.utc) - timedelta(minutes=5)
    monkeypatch.setattr(client, "_deploy_account", AsyncMock(return_value=None))
    monkeypatch.setattr(
        client,
        "_http_get",
        AsyncMock(
            return_value={
                "bid": 99.9,
                "ask": 100.1,
                "time": stale.isoformat(),
            }
        ),
    )

    allowed, slippage, price = await client.validate_slippage(
        "account-1",
        "BTCUSD",
        100.0,
    )

    assert allowed is False
    assert slippage == float("inf")
    assert price is None


@pytest.mark.asyncio
async def test_direct_adapter_call_cannot_bypass_execution_gate(monkeypatch) -> None:
    import services.mt5_client as client

    post = AsyncMock()
    monkeypatch.setattr(client, "_http_post", post)

    result = await client.execute_trade(
        account_id="account-1",
        symbol="BTCUSD",
        direction="long",
        volume=0.1,
        stop_loss=95.0,
        take_profit=110.0,
        signal_entry=100.0,
    )

    assert result["success"] is False
    assert "ExecutionGate" in result["error"]
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_position_size_uses_equity_db_risk_and_broker_step(monkeypatch) -> None:
    from services.mt5_signal_router import MT5SignalRouter

    router = MT5SignalRouter(execution_gate=object())
    monkeypatch.setattr(
        router,
        "_get_user_risk_pct",
        AsyncMock(return_value=1.0),
    )
    info = {
        "equity": 10_000.0,
        "free_margin": 5_000.0,
        "connected": True,
    }
    spec = {
        "trade_allowed": True,
        "contract_size": 100_000.0,
        "tick_size": 0.01,
        "tick_value": 0.10,
        "min_volume": 0.10,
        "max_volume": 20.0,
        "volume_step": 0.10,
    }

    size = await router._calculate_position_size(
        user_id=7,
        entry=100.0,
        stop_loss=99.0,
        account_id="account-7",
        tier="VIP",
        account_info=info,
        symbol_spec=spec,
        symbol="BTCUSD",
    )

    assert size == 10.0


@pytest.mark.asyncio
async def test_position_size_missing_inputs_returns_zero_not_micro_lot() -> None:
    from services.mt5_signal_router import MT5SignalRouter

    router = MT5SignalRouter(execution_gate=object())
    size = await router._calculate_position_size(
        user_id=7,
        entry=100.0,
        stop_loss=99.0,
        account_id="account-7",
        tier="VIP",
        account_info={},
        symbol_spec={},
        symbol="BTCUSD",
    )

    assert size == 0.0


async def _prime_guarded_router(monkeypatch, router) -> AsyncMock:
    import core.redis_state as redis_state
    import services.mt5_client as client

    monkeypatch.setattr(router, "_get_user_tier", lambda _uid: "VIP")
    monkeypatch.setattr(
        router,
        "_get_user_mt5_account",
        AsyncMock(return_value="account-7"),
    )
    monkeypatch.setattr(
        router,
        "_get_user_execution_policy",
        AsyncMock(
            return_value={
                "found": True,
                "consent": True,
                "user_enabled": True,
                "credentials_encrypted": True,
                "mode": "auto",
            }
        ),
    )
    monkeypatch.setattr(
        router,
        "_has_execution_evidence",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        router,
        "_get_user_profile_policy",
        AsyncMock(return_value={"allowed": True, "reason": "ok"}),
    )
    monkeypatch.setattr(
        router,
        "_calculate_position_size",
        AsyncMock(return_value=0.2),
    )
    monkeypatch.setattr(
        router,
        "_reserve_user_execution_quota",
        AsyncMock(return_value=(True, "", 77)),
    )
    monkeypatch.setattr(
        router,
        "_release_user_execution_quota",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(router, "_resource_pressure_clear", lambda: True)
    monkeypatch.setattr(
        client,
        "get_account_info",
        AsyncMock(
            return_value={
                "equity": 10_000.0,
                "free_margin": 9_000.0,
                "connected": True,
                "is_demo": True,
            }
        ),
    )
    monkeypatch.setattr(
        client,
        "get_symbol_specification",
        AsyncMock(
            return_value={
                "trade_allowed": True,
                "contract_size": 100_000.0,
                "tick_size": 0.00001,
                "tick_value": 1.0,
                "min_volume": 0.01,
                "max_volume": 10.0,
                "volume_step": 0.01,
            }
        ),
    )
    monkeypatch.setattr(
        client,
        "get_live_quote",
        AsyncMock(
            return_value={
                "provider": "metaapi",
                "trusted": True,
                "age_seconds": 0.5,
                "max_age_seconds": 15.0,
            }
        ),
    )
    monkeypatch.setattr(
        client,
        "get_reconciliation_snapshot",
        AsyncMock(return_value={"ready": True, "positions": []}),
    )
    monkeypatch.setattr(
        redis_state.state,
        "get_killswitch",
        AsyncMock(return_value=SimpleNamespace(enabled=False)),
    )
    execute = AsyncMock()
    monkeypatch.setattr(router, "_execute_via_mt5", execute)
    return execute


@pytest.mark.asyncio
async def test_router_connects_active_metaapi_path_to_default_off_gate(
    monkeypatch,
) -> None:
    from services.mt5_signal_router import MT5SignalRouter

    monkeypatch.delenv("AUTO_TRADE_ENABLED", raising=False)
    router = MT5SignalRouter()
    execute = await _prime_guarded_router(monkeypatch, router)
    signal = {
        "signal_id": "sig-7",
        "asset": "BTCUSDT",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
    }

    result = await router.route_signal(signal, 7, "auto")

    assert result.success is False
    assert "AUTO_TRADE_DISABLED" in str(result.error)
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_submits_only_after_gate_and_durable_reservation(
    monkeypatch,
) -> None:
    from services.mt5_signal_router import (
        ExecutionResult as RouterExecutionResult,
        MT5SignalRouter,
    )

    gate = ExecutionGate(safety_flags=_enabled_safety_flags())
    router = MT5SignalRouter(execution_gate=gate)
    execute = await _prime_guarded_router(monkeypatch, router)
    execute.return_value = RouterExecutionResult(
        success=True,
        message="executed",
        order_id="order-7",
    )
    reserve = AsyncMock(return_value=True)
    record = AsyncMock(return_value=None)
    monkeypatch.setattr(router, "_reserve_execution_once", reserve)
    monkeypatch.setattr(router, "_record_execution_reservation", record)
    signal = _integrity_signal()

    result = await router.route_signal(signal, 7, "auto")

    assert result.success is True
    assert result.order_id == "order-7"
    reserve.assert_awaited_once()
    execute.assert_awaited_once()
    assert execute.await_args.kwargs["execution_authorized"] is True
    assert execute.await_args.kwargs["idempotency_key"]
    record.assert_awaited_once()
