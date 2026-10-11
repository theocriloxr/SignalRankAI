from __future__ import annotations

import ast
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import time
import logging
from typing import Any

import pytest

from data.provider_types import LivePriceQuote
from engine.delivery_freshness import evaluate_signal_age, evaluate_time_to_telegraph
from engine.delivery_prefilter import analytical_age_expired, prefilter_delivery_candidate
from signalrank_telegram.resend_selection import has_fresh_resend, rank_resend_candidates, take_distinct_fresh_resends


def row(sid: str, score: float, age: float = 1, asset: str = "BTCUSDT") -> SimpleNamespace:
    return SimpleNamespace(signal_id=sid, score=score, asset=asset, timeframe="1m",
                           created_at=datetime.now(timezone.utc)-timedelta(seconds=age), trade_profile="scalp")


def selected(rows, limit=1):
    qualified = [r for r in rank_resend_candidates(rows, 75)
                 if evaluate_signal_age(vars(r)).ok and evaluate_time_to_telegraph(vars(r)).ok]
    return take_distinct_fresh_resends(qualified, limit)


def test_stale_top_score_cannot_hide_fresh_version_of_same_bucket(monkeypatch):
    monkeypatch.setenv("TIME_TO_TELEGRAPH_MAX_SECONDS_CRYPTO_SCALP", "20")
    old, fresh = row("old", 99, 3600), row("fresh", 88)
    assert selected([old, fresh]) == [fresh]


def test_queue_expired_high_scores_cannot_consume_delivery_limit():
    old = [row(str(i), 99-i, 60, asset=f"OLD{i}USDT") for i in range(3)]
    fresh = row("fresh", 88)
    assert evaluate_signal_age(vars(old[0])).ok
    assert not evaluate_time_to_telegraph(vars(old[0])).ok
    assert selected([*old, fresh]) == [fresh]


def test_distinct_slots_keep_highest_fresh_score_and_limit():
    lower, high, eth = row("lower", 80), row("high", 90), row("eth", 85, asset="ETHUSDT")
    assert selected([lower, eth, high], 2) == [high, eth]
    assert selected([lower, eth, high], 1) == [high]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), "invalid", None])
def test_invalid_scores_cannot_displace_valid_retry(bad):
    fresh = row("fresh", 80)
    assert selected([row("invalid", bad), fresh]) == [fresh]


def test_quality_floor_and_identity_still_apply():
    assert selected([row("low", 74), row("", 99), row("noasset", 99, asset="")]) == []
    assert rank_resend_candidates([row("ok", 90)], float("nan")) == []


def test_fresh_backlog_work_preempts_optional_housekeeping():
    backlog = [row(str(i), 99, 3600) for i in range(50)]
    assert not has_fresh_resend(backlog)
    assert has_fresh_resend([*backlog, row("live", 80)])
    assert not has_fresh_resend([row("queue_expired", 90, 60)])


@pytest.fixture
def opportunity(monkeypatch):
    import data.market_hours as hours
    monkeypatch.setattr(hours, "get_market_session_status", lambda _: SimpleNamespace(is_open=True, reason="synthetic open session"))
    now = time.time()
    signal = {"asset": "BTCUSDT", "timeframe": "1m", "trade_profile": "scalp", "direction": "long",
              "entry": 100.0, "stop_loss": 99.0, "take_profit": [103.0], "created_at": datetime.now(timezone.utc)}
    quote = LivePriceQuote("BTCUSDT", 100.0, "coinbase", now, 1, asset_class="crypto",
                           source_timestamp=now, market_status="open", session="continuous",
                           provider_health="healthy", quote_kind="bid_ask", bid=99.99, ask=100.01)
    return signal, quote


@pytest.mark.asyncio
async def test_shared_prefilter_accepts_real_contract_and_preserves_signal(opportunity):
    signal, quote = opportunity
    original = dict(signal)
    result = await prefilter_delivery_candidate(signal, quote)
    assert result.ok and result.live_price == 100.0
    assert "quote_trust_passed" in result.rule_results
    assert "sl_tp_not_resolved" in result.rule_results
    assert signal == original


@pytest.mark.asyncio
@pytest.mark.parametrize("price,direction,stop,target", [(99.0,"long",99.99,100.1), (100.02,"short",100.01,99.9)])
async def test_consumed_stop_is_rejected_before_recipient_work(opportunity, price, direction, stop, target):
    signal, quote = opportunity
    signal.update(direction=direction, stop_loss=stop, take_profit=[target])
    quote = replace(quote, price=price, bid=price, ask=price)
    result = await prefilter_delivery_candidate(signal, quote)
    assert not result.ok
    assert not analytical_age_expired(result.reason)


@pytest.mark.asyncio
async def test_unavailable_quote_does_not_make_second_provider_request(opportunity, monkeypatch):
    import engine.delivery_freshness as freshness
    async def forbidden(*args, **kwargs):
        pytest.fail("prefilter made another provider request")
    monkeypatch.setattr(freshness, "_fetch_final_live_quote", forbidden)
    result = await prefilter_delivery_candidate(opportunity[0], None)
    assert not result.ok and result.reason == "prefilter_quote_unavailable"
    assert not analytical_age_expired(result.reason)


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"symbol":"ETHUSDT"}, {"source_timestamp": None}, {"source_timestamp": 1.0},
    {"provider_health":"unhealthy"}, {"quote_kind":"previous_close"},
])
async def test_quote_failures_remain_closed_and_do_not_expire_analysis(opportunity, changes):
    signal, quote = opportunity
    result = await prefilter_delivery_candidate(signal, replace(quote, **changes))
    assert not result.ok and not analytical_age_expired(result.reason)


@pytest.mark.asyncio
async def test_validation_exception_is_static_and_fail_closed(opportunity, monkeypatch):
    import engine.delivery_prefilter as prefilter
    async def failed(*args, **kwargs):
        raise RuntimeError("secret connection detail must not escape")
    monkeypatch.setattr(prefilter, "validate_delivery_freshness", failed)
    result = await prefilter_delivery_candidate(*opportunity)
    assert not result.ok and result.reason == "prefilter_validation_error:RuntimeError"


@pytest.mark.asyncio
async def test_analytical_and_queue_expiry_have_separate_authority(opportunity):
    signal, quote = opportunity
    signal["created_at"] -= timedelta(seconds=60)
    queue = await prefilter_delivery_candidate(signal, quote)
    assert not queue.ok and queue.state == "EXPIRED_IN_QUEUE"
    assert not analytical_age_expired(queue.reason)
    signal["created_at"] -= timedelta(hours=1)
    analytical = await prefilter_delivery_candidate(signal, quote)
    assert not analytical.ok and analytical_age_expired(analytical.reason)


def test_actual_retry_job_applies_slot_limit_after_both_freshness_checks():
    source = (Path(__file__).resolve().parents[1]/"signalrank_telegram"/"bot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    job = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_resend_unsent_signals_async")
    calls = [node for node in ast.walk(job) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    line = lambda name: next(node.lineno for node in calls if node.func.id == name)
    assert line("rank_resend_candidates") < line("evaluate_signal_age") < line("evaluate_time_to_telegraph") < line("take_distinct_fresh_resends")


def actual_engine_coroutine(name, namespace):
    source = (Path(__file__).resolve().parents[1]/"engine"/"core.py").read_text(encoding="utf-8")
    node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "actual_engine_coroutine", "exec"), namespace)
    return namespace[name]


@pytest.mark.asyncio
async def test_delayed_actual_fanout_uses_original_cycle_and_skips_recipient_queries(monkeypatch, opportunity):
    import engine.delivery_freshness as freshness
    import engine.delivery_prefilter as prefilter
    seen = []
    async def quote(_):
        return opportunity[1]
    async def blocked(signal, quote):
        seen.append(signal["signal_id"])
        return freshness.DeliveryFreshnessResult(False, "prefilter_quote_unavailable")
    monkeypatch.setattr(freshness, "fetch_trusted_live_quote", quote)
    monkeypatch.setattr(prefilter, "prefilter_delivery_candidate", blocked)
    original = [{"signal_id":"original", "asset":"BTCUSDT", "timeframe":"1m"}]
    stats = {}
    namespace = {"scored_signals_all":original,"user_ids":[1],"pipeline_stats":stats,
                 "asyncio":asyncio,"logger":logging.getLogger(__name__),"Any":Any,
                 "_compact_reason":lambda value, **_: str(value),"_env_float":lambda _, default:default}
    fanout = actual_engine_coroutine("deliver_all", namespace)
    pending = fanout()
    original[0]["signal_id"] = "mutated"
    original.clear()
    namespace.update(scored_signals_all=[{"signal_id":"next_cycle"}],user_ids=[2],pipeline_stats={})
    # Any accidental per-user query/import would fail this isolated harness.
    assert await pending == 0
    assert seen == ["original"]
    assert stats["delivery_skip_reasons"] == {"shared_prefilter:prefilter_quote_unavailable":1}


@pytest.mark.asyncio
async def test_actual_fanout_wrapper_keeps_original_callable_and_owned_lock_token():
    events = []
    class State:
        async def cache_delete_if_value(self, key, token):
            events.append((key, token))
            return True
    async def original():
        events.append("original_batch")
        return 7
    async def replaced():
        pytest.fail("old wrapper invoked a subsequent scanner batch")
    namespace = {"deliver_all":original,"_delivery_state":State(),"_lock_key":"original_key",
                 "_lock_token":"original_token","logger":logging.getLogger(__name__)}
    wrapper = actual_engine_coroutine("_deliver_all_with_lock_release", namespace)
    pending = wrapper()
    namespace.update(deliver_all=replaced,_delivery_state=object(),_lock_key="new_key",_lock_token="new_token")
    assert await pending == 7
    assert events == ["original_batch",("original_key","original_token")]
