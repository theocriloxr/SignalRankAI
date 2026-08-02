from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.env import SafetyFlags
from execution.service import ExecutionGate, ExecutionRequest
from services.mt5_signal_router import ExecutionMode, MT5SignalRouter


def _flags() -> SafetyFlags:
    return SafetyFlags(
        auto_trade_enabled=False,
        copy_trade_enabled=False,
        payments_enabled=False,
        telegram_rich_messages_enabled=False,
        vip_webhook_dispatch_enabled=False,
        chat_mt5_credentials_enabled=False,
    )


def _manual_request(**overrides) -> ExecutionRequest:
    values = {
        "user_id": 7,
        "signal_id": "sig-manual",
        "signal": {
            "entry": 100.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "direction": "long",
        },
        "account_id": "account-7",
        "tier": "VIP",
        "mode": "manual_confirmed",
        "user_enabled": True,
        "consent": True,
        "account_ready": True,
        "account_is_demo": True,
        "credentials_encrypted": True,
        "quote_trusted": True,
        "quote_age_seconds": 1.0,
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


def test_manual_confirmed_does_not_depend_on_auto_flag(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_EXECUTION_ENABLED", "1")
    gate = ExecutionGate(safety_flags=_flags())

    decision = gate.preflight(_manual_request())

    assert decision.allowed is True
    assert "AUTO_TRADE_DISABLED" not in decision.reasons


def test_manual_confirmed_still_requires_terms_callback_consent() -> None:
    gate = ExecutionGate(safety_flags=_flags())

    decision = gate.preflight(_manual_request(consent=False))

    assert decision.allowed is False
    assert "user_consent_required" in decision.reasons


@pytest.mark.asyncio
async def test_manual_policy_requires_manual_mode_and_terms(monkeypatch) -> None:
    router = MT5SignalRouter(execution_gate=object())
    # The full SQLAlchemy policy query is integration-tested elsewhere. Here we
    # exercise the route's mode interpretation to prevent AUTO-only regressions.
    monkeypatch.setattr(
        router,
        "_get_user_execution_policy",
        AsyncMock(
            return_value={
                "found": True,
                "accepted_terms": True,
                "consent": True,
                "user_enabled": True,
                "credentials_encrypted": True,
                "mode": ExecutionMode.MANUAL,
            }
        ),
    )
    assert ExecutionMode.MANUAL_CONFIRMED == "manual_confirmed"


def test_telegram_bot_has_no_direct_broker_adapter_call_or_micro_lot_fallback() -> None:
    source = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")

    assert "from services.mt5_client import ensure_user_mt5_account_id, validate_slippage, execute_trade" not in source
    assert "result = await execute_trade(" not in source
    assert "_exec_vol = 0.01" not in source
    assert "equity) or 100.0" not in source
    assert 'execution_mode="manual_confirmed"' in source
    assert 'from services.broker_signal_router import route_signal_to_broker' in source
    assert 'execution_mode=mode' in source

@pytest.mark.asyncio
async def test_manual_confirmed_routes_through_gate_without_auto_optin(monkeypatch) -> None:
    import core.redis_state as redis_state
    import services.market_intelligence as market_intelligence
    import services.mt5_client as client
    from services.mt5_signal_router import ExecutionResult as RouterResult

    gate = ExecutionGate(safety_flags=_flags())
    router = MT5SignalRouter(execution_gate=gate)
    monkeypatch.setenv("DEMO_EXECUTION_ENABLED", "1")
    monkeypatch.setattr(router, "_get_user_tier", lambda _uid: "VIP")
    monkeypatch.setattr(router, "_get_user_mt5_account", AsyncMock(return_value="acct"))
    monkeypatch.setattr(
        router,
        "_get_user_execution_policy",
        AsyncMock(
            return_value={
                "found": True,
                "accepted_terms": True,
                "consent": True,
                "user_enabled": True,
                "credentials_encrypted": True,
                "mode": "manual",
            }
        ),
    )
    monkeypatch.setattr(
        router,
        "_get_user_profile_policy",
        AsyncMock(return_value={"allowed": True, "reason": "profile_match"}),
    )
    monkeypatch.setattr(router, "_has_execution_evidence", AsyncMock(return_value=True))
    monkeypatch.setattr(router, "_calculate_position_size", AsyncMock(return_value=0.2))
    monkeypatch.setattr(router, "_reserve_execution_once", AsyncMock(return_value=True))
    monkeypatch.setattr(
        router,
        "_reserve_user_execution_quota",
        AsyncMock(return_value=(True, "", 1)),
    )
    monkeypatch.setattr(router, "_record_execution_reservation", AsyncMock())
    monkeypatch.setattr(router, "_resource_pressure_clear", lambda: True)
    monkeypatch.setattr(
        market_intelligence,
        "evaluate_market",
        lambda *_args, **_kwargs: SimpleNamespace(
            market_open=True,
            trading_allowed=True,
        ),
    )
    monkeypatch.setattr(
        client,
        "get_account_info",
        AsyncMock(
            return_value={
                "connected": True,
                "equity": 10000.0,
                "free_margin": 9000.0,
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
                "age_seconds": 0.1,
                "max_age_seconds": 15.0,
            }
        ),
    )
    monkeypatch.setattr(
        client,
        "get_reconciliation_snapshot",
        AsyncMock(return_value={"ready": True}),
    )
    monkeypatch.setattr(
        redis_state.state,
        "get_killswitch",
        AsyncMock(return_value=SimpleNamespace(enabled=False)),
    )
    execute = AsyncMock(
        return_value=RouterResult(
            success=True,
            message="executed",
            order_id="manual-order",
        )
    )
    monkeypatch.setattr(router, "_execute_via_mt5", execute)

    result = await router.route_signal(
        {
            "signal_id": "sig-manual",
            "asset": "EURUSD",
            "direction": "long",
            "entry": 1.1,
            "stop_loss": 1.09,
            "take_profit": [1.12],
        },
        7,
        "manual_confirmed",
    )

    assert result.success is True
    assert result.order_id == "manual-order"
    assert execute.await_args.kwargs["execution_mode"] == "manual_confirmed"
    assert execute.await_args.kwargs["execution_authorized"] is True


@pytest.mark.asyncio
async def test_execute_via_mt5_records_canonical_ledger_once(monkeypatch) -> None:
    import services.mt5_client as client

    router = MT5SignalRouter(execution_gate=object())
    monkeypatch.setattr(
        client,
        "execute_trade",
        AsyncMock(
            return_value={
                "success": True,
                "order_id": "broker-order",
                "live_price": 100.1,
                "hard_stop_attached": True,
            }
        ),
    )
    ledger = AsyncMock(return_value=True)
    paper = AsyncMock(return_value=None)
    monkeypatch.setattr(router, "_record_execution_ledger", ledger)
    monkeypatch.setattr(router, "_sync_to_paper_ledger", paper)

    result = await router._execute_via_mt5(
        signal={
            "signal_id": "sig-ledger",
            "asset": "BTCUSD",
            "direction": "long",
            "entry": 100.0,
            "stop_loss": 95.0,
            "take_profit": [110.0],
        },
        user_id=7,
        volume=0.2,
        account_id="acct",
        tier="VIP",
        execution_mode="manual_confirmed",
        execution_authorized=True,
        idempotency_key="idem",
    )

    assert result.success is True
    assert result.order_id == "broker-order"
    ledger.assert_awaited_once()
    paper.assert_awaited_once()
