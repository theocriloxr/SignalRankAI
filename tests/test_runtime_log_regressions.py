import asyncio
import logging

import pytest


@pytest.mark.asyncio
async def test_ml_training_clips_extreme_r_and_preserves_raw_value(monkeypatch):
    import sqlalchemy
    import db.models as models
    from engine.ml_logger import log_ml_training_data

    captured = {}

    class FakeSelect:
        def where(self, *_args, **_kwargs):
            return self

    class Result:
        def scalar_one_or_none(self):
            return None

    class Session:
        async def execute(self, _statement):
            return Result()

        def add(self, row):
            captured.update({
                "outcome_r_multiple": row.outcome_r_multiple,
                "outcome_meta": row.outcome_meta,
            })

        async def commit(self):
            return None

        async def rollback(self):
            return None

    monkeypatch.setattr(sqlalchemy, "select", lambda *_args, **_kwargs: FakeSelect())
    monkeypatch.setenv("TRAINING_R_CLIP_MIN", "-5")
    monkeypatch.setenv("TRAINING_R_CLIP_MAX", "10")

    ok = await log_ml_training_data(
        Session(),
        signal_id="signal-1",
        asset="XRPUSDT",
        timeframe="5m",
        direction="long",
        entry=1.0,
        stop_loss=0.99,
        take_profit="[]",
        ml_probability=0.7,
        outcome_status="loss",
        outcome_r_multiple=-43.87,
        outcome_meta={"tp1_hit": False},
    )

    assert ok is True
    assert captured["outcome_r_multiple"] == -5.0
    assert captured["outcome_meta"]["raw_r_multiple"] == -43.87
    assert captured["outcome_meta"]["r_clipped"] is True


@pytest.mark.asyncio
async def test_ml_training_accepts_missing_r_without_format_error(monkeypatch):
    import sqlalchemy
    import db.models as models
    from engine.ml_logger import log_ml_training_data

    class FakeSelect:
        def where(self, *_args, **_kwargs):
            return self

    class Result:
        def scalar_one_or_none(self):
            return None

    class Session:
        async def execute(self, _statement):
            return Result()

        def add(self, _row):
            return None

        async def commit(self):
            return None

        async def rollback(self):
            return None

    monkeypatch.setattr(sqlalchemy, "select", lambda *_args, **_kwargs: FakeSelect())
    assert await log_ml_training_data(
        Session(), "signal-2", "BTCUSDT", "1h", "long", 1.0, 0.9,
        "[]", 0.5, "time_stop", outcome_r_multiple=None,
    )


@pytest.mark.asyncio
async def test_telegram_background_task_exception_is_consumed(caplog):
    from signalrank_telegram.bot import _consume_telegram_task_result

    async def fail():
        raise TimeoutError("telegram timeout")

    task = asyncio.create_task(fail())
    with caplog.at_level(logging.WARNING):
        await asyncio.sleep(0)
        _consume_telegram_task_result(task)

    assert "background send failed" in caplog.text


def test_lifecycle_blocks_tp_and_sl_before_entry():
    from engine.signal_lifecycle import evaluate_observation

    assert evaluate_observation(
        state="WATCHING_FOR_ENTRY",
        direction="long",
        entry=100,
        stop_loss=95,
        tp_levels=[105, 110, 115],
        current_price=96,
    ) == []


def test_buy_and_sell_lifecycle_transitions():
    from engine.signal_lifecycle import evaluate_observation

    buy_events = evaluate_observation(
        state="WATCHING_FOR_ENTRY", direction="long", entry=100, stop_loss=95,
        tp_levels=[105, 110, 115], current_price=106, high=106, low=99,
    )
    sell_events = evaluate_observation(
        state="WATCHING_FOR_ENTRY", direction="short", entry=100, stop_loss=105,
        tp_levels=[95, 90, 85], current_price=94, high=101, low=94,
    )

    assert buy_events == ["entry_touched", "tp1_hit"]
    assert sell_events == ["entry_touched", "tp1_hit"]


def test_tp1_then_break_even_is_protected_exit():
    from engine.signal_lifecycle import evaluate_observation

    events = evaluate_observation(
        state="TP1_HIT", direction="long", entry=100, stop_loss=100,
        tp_levels=[105, 110, 115], current_price=100, highest_tp_hit=1,
    )
    assert events == ["breakeven_stop"]


def test_expiry_before_entry_is_missed_entry_not_loss():
    from engine.signal_lifecycle import evaluate_observation

    events = evaluate_observation(
        state="WATCHING_FOR_ENTRY", direction="long", entry=100, stop_loss=95,
        tp_levels=[105], current_price=97, expired=True,
    )
    assert events == ["missed_entry"]


def test_event_notification_schema_is_idempotent_per_recipient():
    from db.models import SignalEventNotification

    constraints = {
        constraint.name for constraint in SignalEventNotification.__table__.constraints
        if getattr(constraint, "name", None)
    }
    assert "uq_signal_event_notification_recipient" in constraints


def test_timezone_display_uses_receiver_zone():
    from datetime import datetime, timezone
    from signalrank_telegram.timezones import format_user_datetime

    value = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    assert "1:00 PM WAT" in format_user_datetime(value, "Africa/Lagos")


def test_okx_normalized_candles_are_usable_market_data():
    from data.market_data import usable_timeframe_payloads

    candles = [
        {
            "timestamp": 1_720_000_000_000 + index * 300_000,
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100.5 + index,
            "volume": 1000,
        }
        for index in range(30)
    ]
    payload = {"5m": {"candles": candles, "source": "okx_connector"}}
    assert list(usable_timeframe_payloads(payload)) == ["5m"]


@pytest.mark.asyncio
async def test_okx_adapter_normalizes_provider_rows(monkeypatch):
    from data.connectors import okx_adapter

    rows = [
        [str(1_720_000_000_000 + index * 300_000), "100", "101", "99", "100.5", "42"]
        for index in range(30)
    ]

    class Response:
        status_code = 200

        def json(self):
            return {"code": "0", "data": list(reversed(rows))}

    class Client:
        async def get(self, *_args, **_kwargs):
            return Response()

    async def no_retry(call, **_kwargs):
        return await call()

    monkeypatch.setattr(okx_adapter.httpx_client, "get_client", lambda _name: Client())
    monkeypatch.setattr(okx_adapter.httpx_client, "retry_async", no_retry)

    candles = await okx_adapter._async_get_candles("BTCUSDT", "5m", timeout=2)
    assert len(candles) == 30
    assert set(candles[0]) == {"timestamp", "open", "high", "low", "close", "volume"}
    assert candles[0]["timestamp"] < candles[-1]["timestamp"]
