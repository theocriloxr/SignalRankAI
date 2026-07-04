import asyncio
import logging

import pytest


@pytest.mark.asyncio
async def test_ml_training_clips_extreme_r_and_preserves_raw_value(monkeypatch):
    import db.models as models
    from engine.ml_logger import log_ml_training_data

    captured = {}

    class TrainingRow:
        signal_id = "signal_id"

        def __init__(self, **kwargs):
            captured.update(kwargs)

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

    monkeypatch.setattr(models, "MLPastTrainingData", TrainingRow)
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
    import db.models as models
    from engine.ml_logger import log_ml_training_data

    class TrainingRow:
        signal_id = "signal_id"

        def __init__(self, **_kwargs):
            pass

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

    monkeypatch.setattr(models, "MLPastTrainingData", TrainingRow)
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
