from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from engine.trade_manager import TradeManager


@pytest.mark.asyncio
async def test_breakeven_persists_and_does_not_claim_guaranteed_profit() -> None:
    manager = TradeManager()
    trade = {
        "asset": "BTCUSDT",
        "direction": "long",
        "entry": 100.0,
        "take_profit": [110.0],
        "stop_loss": 95.0,
    }
    persist = AsyncMock()
    result = await manager.process_active_trades(
        [trade],
        AsyncMock(return_value=110.0),
        persist_fn=persist,
    )
    assert result[0]["sl_moved_to_be"] is True
    assert result[0]["stop_loss"] == 100.0
    persist.assert_awaited_once_with(trade)


@pytest.mark.asyncio
async def test_broker_rejection_does_not_mutate_stop() -> None:
    manager = TradeManager()
    trade = {
        "asset": "EURUSD",
        "direction": "long",
        "entry": 1.10,
        "take_profit": [1.20],
        "stop_loss": 1.05,
        "mt5_ticket": 42,
    }
    persist = AsyncMock()
    modify = AsyncMock(return_value=(False, "rejected"))
    result = await manager.process_active_trades(
        [trade],
        AsyncMock(return_value=1.20),
        persist_fn=persist,
        modify_sl_fn=modify,
    )
    assert result[0]["stop_loss"] == 1.05
    assert "sl_moved_to_be" not in result[0]
    persist.assert_not_awaited()
