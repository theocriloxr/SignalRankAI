"""The ML model's lifecycle is recorded and visible (owner request 9 Nov 2026: 'fix the ML model').

Production served the 29 Sep champion for six weeks; live median probability
1-3% against realised TP1 rates of 10-75%. Why it was not replaced could not be
read: a skipped or rejected training run left no durable trace.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import pytest

from ml import lifecycle_status as ls


class _State:
    def __init__(self):
        self.data = {}

    def set_sync(self, key, value, ex=None):
        self.data[key] = value

    def get_sync(self, key):
        return self.data.get(key)


@pytest.fixture()
def state(monkeypatch):
    from core import redis_state

    fake = _State()
    monkeypatch.setattr(redis_state, "state", fake)
    return fake


def test_a_skipped_run_is_recorded_with_its_reason(state):
    async def skipped_main(lookback_days=None):
        logging.getLogger("ml.train_model").info(
            "[ml_training_run] id=ml-1 status=skipped reason=active_candidate_forward_lease candidate=abc "
            "status_detail=eligible observations=120 resolved=60 primary_model_preserved=true")
        return True

    assert asyncio.run(ls.run_and_record(skipped_main)) is True
    record = json.loads(state.data[ls.LAST_RUN_KEY])
    assert record["status"] == "skipped" and record["reason"] == "active_candidate_forward_lease"
    assert "/ml_candidate_promote CONFIRM" in ls.explain(record)


def test_a_crash_is_recorded_and_still_raised(state):
    async def broken(lookback_days=None):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        asyncio.run(ls.run_and_record(broken))
    assert "training crashed" in ls.explain(json.loads(state.data[ls.LAST_RUN_KEY]))


def test_readiness_and_alert_flag_a_six_week_old_champion(state, monkeypatch):
    ls.record_champion({"trained_at": "2026-09-29T19:40:45", "version": "1.0.0", "validated": True})
    status = ls.lifecycle_status(now=datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc))
    assert status["ok"] is True and status["stale"] is True and status["champion_age_days"] == 40.9
    assert status["why_not_replaced"] == "no training run recorded since this check was added"

    from observability import owner_alerts

    monkeypatch.setattr(owner_alerts, "_owner_ids", lambda: [42])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setattr("core.health_notifications.claim_health_notification", lambda *a, **k: (True, None))
    sent = []
    finding = owner_alerts.ml_stale_finding(force=True)
    assert finding is not None
    owner_alerts.ml_stale_alert(finding, post=lambda token, chat, text: sent.append(text) or True)
    assert sent and "ML model is stale" in sent[0] and "/ml_candidate_promote CONFIRM" in sent[0]


def test_training_main_is_wrapped():
    from ml import train_model

    assert "_main_impl" in train_model.main.__code__.co_names or "run_and_record" in train_model.main.__code__.co_names
