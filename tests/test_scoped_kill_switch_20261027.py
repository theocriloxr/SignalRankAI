"""CX-RISK-04: strategy, instrument and asset-class execution kill switches.

Only the global switch existed. Scoped switches add blocks for one strategy,
one instrument or one asset class, are audited, and fail closed when their
store cannot be read, exactly like the global switch.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

import core.scoped_kill_switch as scoped
import web.platform_api as platform_api
from core.redis_state import state as shared_state

ROOT = Path(__file__).resolve().parents[1]


class FakeState:
    def __init__(self, document=None, broken=False):
        self.document = document or {}
        self.broken = broken
        self.writes = 0

    async def get_scoped_killswitches(self):
        if self.broken:
            raise RuntimeError("store down")
        return dict(self.document)

    async def set_scoped_killswitches(self, document):
        self.document = dict(document)
        self.writes += 1


def test_keys_are_canonicalised_so_aliases_hit_the_same_switch():
    assert scoped.normalize_key("asset_class", "fx") == scoped.normalize_key("asset_class", "Forex") == "FOREX"
    assert scoped.normalize_key("instrument", "btc/usdt") == "BTCUSDT"
    assert scoped.normalize_key("strategy", "trend_follow_v2") == "TREND_FOLLOW_V2"
    for scope, key in (("portfolio", "x"), ("asset_class", "crypto-ish"), ("strategy", ""), ("strategy", "a b;drop")):
        with pytest.raises(ValueError):
            scoped.normalize_key(scope, key)


def test_changes_are_audited_bounded_and_require_an_actor():
    document = scoped.apply_change({}, scope="instrument", key="XAUTUSDT", active=True, actor="owner:1",
                                   reason="feed incident", now=100.0)
    assert document["switches"]["instrument"]["XAUTUSDT"]["actor"] == "owner:1"
    released = scoped.apply_change(document, scope="instrument", key="xautusdt", active=False, actor="owner:2", now=200.0)
    assert released["switches"]["instrument"] == {}
    assert [(e["action"], e["actor"], e["was_active"]) for e in released["audit"]] == [
        ("engage", "owner:1", False), ("release", "owner:2", True)]
    for index in range(scoped.AUDIT_LIMIT + 50):
        released = scoped.apply_change(released, scope="strategy", key=f"S{index}", active=True, actor="owner:1")
    assert len(released["audit"]) == scoped.AUDIT_LIMIT
    with pytest.raises(ValueError):
        scoped.apply_change({}, scope="strategy", key="S1", active=True, actor=" ")


def test_matching_signals_are_blocked_and_others_are_not():
    document = scoped.apply_change({}, scope="asset_class", key="fx", active=True, actor="owner:1")
    document = scoped.apply_change(document, scope="strategy", key="mean_reversion", active=True, actor="owner:1")
    block = lambda signal: asyncio.run(scoped.execution_block_reason(signal, state=FakeState(document)))  # noqa: E731
    assert block({"asset": "EURUSD"}) == "scoped_kill_switch:asset_class:FOREX"
    assert block({"asset": "BTCUSDT", "strategy": "mean_reversion"}) == "scoped_kill_switch:strategy:MEAN_REVERSION"
    assert block({"asset": "BTCUSDT", "strategy": "breakout"}) is None


def test_unreadable_store_blocks_execution():
    reason = asyncio.run(scoped.execution_block_reason({"asset": "BTCUSDT"}, state=FakeState(broken=True)))
    assert reason == scoped.UNAVAILABLE


def test_postgres_read_failure_raises_instead_of_reading_as_clear(monkeypatch):
    monkeypatch.setattr(shared_state, "_get_redis_sync", lambda: None)
    monkeypatch.setattr(shared_state, "_pg_available", lambda: True)
    monkeypatch.setattr(shared_state, "_pg_exec_one", lambda *_a, **_k: None)
    with pytest.raises(RuntimeError):
        shared_state.get_scoped_killswitches_sync()


def test_memory_store_round_trip(monkeypatch):
    monkeypatch.setattr(shared_state, "_get_redis_sync", lambda: None)
    monkeypatch.setattr(shared_state, "_pg_available", lambda: False)
    monkeypatch.setattr(shared_state, "_memory", {})
    document = scoped.apply_change({}, scope="instrument", key="ETHUSDT", active=True, actor="owner:1")
    shared_state.set_scoped_killswitches_sync(document)
    assert shared_state.get_scoped_killswitches_sync()["switches"]["instrument"]["ETHUSDT"]["actor"] == "owner:1"


def test_both_execution_chokepoints_consult_scoped_switches_after_the_global_one():
    for path, marker in (("services/mt5_signal_router.py", "kill_state = await state.get_killswitch()"),
                         ("services/bybit_signal_router.py", "kill_state = await state.get_killswitch()")):
        source = (ROOT / path).read_text(encoding="utf-8")
        start = source.index(marker)
        window = source[start: start + 900]
        assert "execution_block_reason(signal" in window, path
        assert window.index("if not kill_switch:") < window.index("kill_switch = True", window.index("scoped_block"))


def _owner(monkeypatch, fake, authority="OWNER", auth_age=10.0):
    monkeypatch.setattr(platform_api, "_platform_operator_authority", lambda _user: authority)
    monkeypatch.setattr(shared_state, "get_scoped_killswitches", fake.get_scoped_killswitches)
    monkeypatch.setattr(shared_state, "set_scoped_killswitches", fake.set_scoped_killswitches)
    return {"id": 7, "public_user_id": "usr_7", "auth_age_seconds": auth_age}


def _call(user, **payload):
    request = platform_api.OperatorScopedKillSwitchRequest(**payload)
    return asyncio.run(platform_api.operator_scoped_kill_switch(request, user=user))


def test_operator_endpoint_engages_with_confirmation_and_records_actor(monkeypatch):
    fake = FakeState()
    user = _owner(monkeypatch, fake)
    result = _call(user, action="on", scope="instrument", key="btcusdt", reason="halt", confirm=True)
    assert result["switches"]["instrument"]["BTCUSDT"]["actor"] == "owner:usr_7"
    assert result["audit"][-1]["action"] == "engage" and fake.writes == 1


def test_operator_endpoint_refuses_non_owner_unconfirmed_stale_session_and_bad_keys(monkeypatch):
    fake = FakeState()
    with pytest.raises(HTTPException) as exc:
        _call(_owner(monkeypatch, fake, authority="ADMIN"), action="on", scope="instrument", key="BTCUSDT", confirm=True)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        _call(_owner(monkeypatch, fake), action="on", scope="instrument", key="BTCUSDT")
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        _call(_owner(monkeypatch, fake, auth_age=99_999), action="on", scope="instrument", key="BTCUSDT", confirm=True)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        _call(_owner(monkeypatch, fake), action="on", scope="asset_class", key="not-a-class", confirm=True)
    assert exc.value.status_code == 422
    assert fake.writes == 0


def test_operator_endpoint_reports_unavailable_store(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call(_owner(monkeypatch, FakeState(broken=True)), action="status")
    assert exc.value.status_code == 503
