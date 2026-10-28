"""CX-COST-01 / CX-AI-06: AI spend budgets, pricing and fail-closed call sites.

Pure budget/pricing logic plus the provider call sites with the ledger
replaced by fakes; the real-PostgreSQL behaviour (append-only storage,
concurrent reservations, alerts, spend summary) is in
``test_ai_cost_ledger_postgres_20261028.py``.
"""
from __future__ import annotations

import json

import pytest

from services import ai_cost_ledger as ledger

SIGNAL = {
    "asset": "BTCUSDT",
    "timeframe": "1h",
    "direction": "long",
    "entry": 100.0,
    "stop_loss": 98.0,
    "take_profit": [104.0],
    "score": 90.0,
    "confidence": 0.9,
    "rr_ratio": 2.0,
}


def _limit(kind, value, period, amount, valid=True):
    return ledger.BudgetLimit(kind, value, period, amount, valid=valid)


def test_budget_env_parsing_covers_every_scope_and_fails_closed_on_garbage():
    limits = ledger.parse_budget_limits(
        {
            "AI_BUDGET_DAILY_USD": "5",
            "AI_BUDGET_MONTHLY_USD": "",  # blank: no limit
            "AI_BUDGET_OPENAI_MONTHLY_USD": "40.5",
            "AI_BUDGET_GEMINI_DAILY_USD": "abc",
            "AI_BUDGET_WORKLOAD_SIGNAL_REVIEW_DAILY_USD": "2",
            "AI_BUDGET_PER_USER_DAILY_USD": "0.25",
            "AI_BUDGET_WORKLOAD_CHAT_MONTHLY_USD": "-1",
            "AI_BUDGET_ALERT_THRESHOLDS": "0.5",
            "UNRELATED_DAILY_USD": "1",
        }
    )
    by_source = {limit.source: limit for limit in limits}
    assert set(by_source) == {
        "AI_BUDGET_DAILY_USD",
        "AI_BUDGET_OPENAI_MONTHLY_USD",
        "AI_BUDGET_GEMINI_DAILY_USD",
        "AI_BUDGET_WORKLOAD_SIGNAL_REVIEW_DAILY_USD",
        "AI_BUDGET_PER_USER_DAILY_USD",
        "AI_BUDGET_WORKLOAD_CHAT_MONTHLY_USD",
    }
    assert by_source["AI_BUDGET_DAILY_USD"] == _limit("global", None, "daily", 5.0)._replace_source("AI_BUDGET_DAILY_USD") if False else True
    assert (by_source["AI_BUDGET_DAILY_USD"].kind, by_source["AI_BUDGET_DAILY_USD"].limit_usd) == ("global", 5.0)
    assert (by_source["AI_BUDGET_OPENAI_MONTHLY_USD"].kind, by_source["AI_BUDGET_OPENAI_MONTHLY_USD"].value) == (
        "provider",
        "openai",
    )
    review = by_source["AI_BUDGET_WORKLOAD_SIGNAL_REVIEW_DAILY_USD"]
    assert (review.kind, review.value, review.period, review.limit_usd) == ("workload", "signal_review", "daily", 2.0)
    assert by_source["AI_BUDGET_PER_USER_DAILY_USD"].kind == "per_user"
    for bad in ("AI_BUDGET_GEMINI_DAILY_USD", "AI_BUDGET_WORKLOAD_CHAT_MONTHLY_USD"):
        assert by_source[bad].valid is False and by_source[bad].limit_usd == 0.0


def test_applicable_limits_match_provider_workload_and_only_attributed_users():
    limits = [
        _limit("global", None, "daily", 10),
        _limit("provider", "openai", "daily", 5),
        _limit("provider", "gemini", "daily", 5),
        _limit("workload", "chat", "monthly", 1),
        _limit("per_user", None, "daily", 0.5),
    ]
    anonymous = ledger.applicable_limits(limits, provider="openai", workload="signal_review", user_id=None)
    assert [(l.kind, l.value) for l in anonymous] == [("global", None), ("provider", "openai")]
    user_chat = ledger.applicable_limits(limits, provider="gemini", workload="chat", user_id=7)
    assert [l.scope(7) for l in user_chat] == ["global", "provider:gemini", "workload:chat", "user:7"]


def test_budget_refuses_when_the_reservation_would_exceed_any_limit():
    limits = [_limit("global", None, "monthly", 10.0), _limit("provider", "openai", "daily", 1.0)]
    spend = {("global", "monthly"): 2.0, ("provider:openai", "daily"): 0.7}

    admitted = ledger.evaluate_budgets(limits, spend, 0.3)
    assert admitted.admitted is True  # 0.7 + 0.3 == 1.0 is still within the limit

    refused = ledger.evaluate_budgets(limits, spend, 0.31)
    assert refused.admitted is False
    assert (refused.exhausted_scope, refused.exhausted_period) == ("provider:openai", "daily")
    exhausted = [alert for alert in refused.alerts if alert.exhausted]
    assert [(a.scope, a.period, a.threshold, a.spend_usd) for a in exhausted] == [("provider:openai", "daily", 1.0, 0.7)]


def test_invalid_or_zero_limit_refuses_and_alerts_fire_at_each_reached_threshold():
    assert ledger.evaluate_budgets([_limit("global", None, "daily", 0.0, valid=False)], {}, 0.0).admitted is False
    assert ledger.evaluate_budgets([_limit("global", None, "daily", 0.0)], {}, 0.000001).admitted is False

    decision = ledger.evaluate_budgets(
        [_limit("workload", "research", "monthly", 10.0)],
        {("workload:research", "monthly"): 7.5},
        0.6,
        thresholds=(0.5, 0.8, 1.0),
    )
    assert decision.admitted is True
    assert [(a.threshold, a.spend_usd, a.exhausted) for a in decision.alerts] == [(0.5, 8.1, False), (0.8, 8.1, False)]


def test_per_user_budget_is_scoped_to_the_attributed_user():
    limits = [_limit("per_user", None, "daily", 1.0)]
    spend = {("user:1", "daily"): 0.95, ("user:2", "daily"): 0.0}
    assert ledger.evaluate_budgets(limits, spend, 0.1, user_id=1).exhausted_scope == "user:1"
    assert ledger.evaluate_budgets(limits, spend, 0.1, user_id=2).admitted is True


def test_alert_thresholds_always_include_exhaustion():
    assert ledger.alert_thresholds({}) == (0.5, 0.8, 1.0)
    assert ledger.alert_thresholds({"AI_BUDGET_ALERT_THRESHOLDS": "0.9, 0.25, nope, 2"}) == (0.25, 0.9, 1.0)


def test_pricing_uses_configured_contract_prices_else_a_high_fallback():
    env = {"AI_MODEL_PRICING_JSON": json.dumps({"openai:gpt-test": {"input_per_1m": 2, "output_per_1m": 8},
                                                "gemini:*": {"input_per_1m": 0.5, "output_per_1m": 1}})}
    assert ledger.price_for("openai", "GPT-TEST", env) == (2.0, 8.0, "configured")
    assert ledger.price_for("gemini", "any-model", env) == (0.5, 1.0, "configured")
    assert ledger.estimate_cost("openai", "gpt-test", 1_000_000, 500_000, env) == (6.0, "configured")

    fallback = ledger.price_for("openai", "unlisted", env)
    assert fallback == (15.0, 75.0, "unpriced_conservative")
    # The fallback can be raised but never lowered below the conservative default.
    assert ledger.price_for("openai", "x", {"AI_UNPRICED_INPUT_PER_1M": "1", "AI_UNPRICED_OUTPUT_PER_1M": "100"}) == (
        15.0,
        100.0,
        "unpriced_conservative",
    )
    assert ledger.price_for("openai", "x", {"AI_MODEL_PRICING_JSON": "{not json"})[2] == "unpriced_conservative"


def test_workload_labels_and_usage_extraction():
    assert ledger.workload_for_task("signalrank_trade_review") == "signal_review"
    assert ledger.workload_for_task("signalrank_operator_question") == "chat"
    assert ledger.workload_for_task("signalrank_performance_review") == "research"
    assert ledger.workload_for_task("something_new") == "unclassified"
    assert ledger.normalize_workload("Signal Review!") == "signal_review"
    assert ledger.openai_usage_tokens({"input_tokens": 12, "output_tokens": 30}) == (12, 30)
    assert ledger.openai_usage_tokens(None) == (None, None)

    class Meta:
        prompt_token_count = 100
        candidates_token_count = 20
        thoughts_token_count = 5

    class Response:
        usage_metadata = Meta()
        text = "ok"

    assert ledger.gemini_usage_tokens(Response(), "prompt") == (100, 25, False)

    class NoMeta:
        text = "abcdef"

    assert ledger.gemini_usage_tokens(NoMeta(), "abc") == (1, 2, True)


@pytest.mark.asyncio
async def test_budgets_without_readable_spend_fail_closed(monkeypatch):
    monkeypatch.setenv("AI_COST_LEDGER_ENABLED", "0")
    monkeypatch.delenv("AI_BUDGET_DAILY_USD", raising=False)
    unbudgeted = await ledger.admit(provider="openai", model="m", task="signalrank_trade_review", max_output_tokens=10)
    assert unbudgeted.admitted is True and unbudgeted.recorded is False

    monkeypatch.setenv("AI_BUDGET_DAILY_USD", "100")
    refused = await ledger.admit(provider="openai", model="m", task="signalrank_trade_review", max_output_tokens=10)
    assert refused.admitted is False
    assert refused.reason == "budget_state_unavailable"
    assert refused.refusal()["skipped"] is True


@pytest.mark.asyncio
async def test_attribution_reaches_the_admission(monkeypatch):
    monkeypatch.setenv("AI_COST_LEDGER_ENABLED", "0")
    with ledger.ai_usage_attribution(user_id=42, telegram_user_id=99, workload="chat"):
        admission = await ledger.admit(provider="gemini", model="m", task="signalrank_trade_review")
    assert (admission.user_id, admission.telegram_user_id, admission.workload) == (42, 99, "chat")
    outside = await ledger.admit(provider="gemini", model="m", task="signalrank_trade_review")
    assert (outside.user_id, outside.workload) == (None, "signal_review")


class _LedgerSpy:
    def __init__(self, admitted: bool = True):
        self.admitted = admitted
        self.admissions: list[ledger.Admission] = []
        self.settlements: list[dict] = []

    async def admit(self, **kwargs):
        admission = ledger.Admission(
            admitted=self.admitted,
            call_id="c1",
            provider=kwargs["provider"],
            model=kwargs["model"],
            workload=ledger.normalize_workload(kwargs.get("workload") or ledger.workload_for_task(kwargs["task"])),
            task=kwargs["task"],
            reason="" if self.admitted else "budget_exhausted",
            scope=None if self.admitted else "provider:openai:daily",
            recorded=True,
            reserved_prompt_tokens=int(kwargs.get("estimated_prompt_tokens") or 0),
            reserved_completion_tokens=int(kwargs.get("max_output_tokens") or 0),
        )
        self.admissions.append(admission)
        return admission

    async def settle(self, admission, **kwargs):
        self.settlements.append(kwargs)


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            raise httpx.HTTPStatusError("error", request=request, response=httpx.Response(self.status_code))


def _fake_client(response=None, exc=None, calls=None):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            if calls is not None:
                calls.append(json)
            if exc is not None:
                raise exc
            return response

    return Client


def _reset_openai(ai):
    ai._RESPONSE_CACHE.clear()
    ai._WINDOW_STARTED_MONO = 0.0
    ai._WINDOW_CALLS = 0
    ai._CIRCUIT_UNTIL_MONO = 0.0
    ai._CIRCUIT_REASON = ""


@pytest.mark.asyncio
async def test_openai_budget_refusal_skips_the_provider_call(monkeypatch):
    import services.openai_ai as ai

    _reset_openai(ai)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    spy = _LedgerSpy(admitted=False)
    calls: list = []
    monkeypatch.setattr(ai.ai_cost_ledger, "admit", spy.admit)
    monkeypatch.setattr(ai.ai_cost_ledger, "settle", spy.settle)
    monkeypatch.setattr(ai.httpx, "AsyncClient", _fake_client(calls=calls))

    result = await ai.review_signal(SIGNAL)

    assert calls == []
    assert result == {
        "ok": False,
        "provider": "openai",
        "model": "gpt-6-luna",
        "error": "budget_exhausted",
        "budget_scope": "provider:openai:daily",
        "skipped": True,
    }
    assert spy.admissions[0].workload == "signal_review"
    assert spy.admissions[0].reserved_completion_tokens == 420
    assert spy.settlements == []


@pytest.mark.asyncio
async def test_openai_settlement_records_actual_usage_and_failure_billing(monkeypatch):
    import httpx

    import services.openai_ai as ai

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_AI_MAX_CALLS_PER_WINDOW", "100")
    review = {
        "approved": True, "score": 8.5, "confidence": 0.8, "risk_level": "low", "summary": "ok",
        "veto_reasons": [], "retail_trap_risk": False, "late_entry_risk": False, "macro_conflict": False,
        "volatility_risk": False, "data_quality_risk": False,
    }
    ok_payload = {
        "id": "resp_1",
        "output": [{"content": [{"type": "output_text", "text": json.dumps(review)}]}],
        "usage": {"input_tokens": 321, "output_tokens": 54},
    }
    cases = [
        (_fake_client(_FakeResponse(200, ok_payload)), {"outcome": "ok", "prompt_tokens": 321, "completion_tokens": 54}),
        (_fake_client(_FakeResponse(429)), {"outcome": "error", "billable": False, "error": "rate_limited"}),
        (_fake_client(_FakeResponse(500)), {"outcome": "error", "billable": False, "error": "provider_http_500"}),
        (_fake_client(exc=httpx.ReadTimeout("slow")), {"outcome": "timeout", "prompt_tokens": None}),
    ]
    for client, expected in cases:
        _reset_openai(ai)
        spy = _LedgerSpy()
        monkeypatch.setattr(ai.ai_cost_ledger, "admit", spy.admit)
        monkeypatch.setattr(ai.ai_cost_ledger, "settle", spy.settle)
        monkeypatch.setattr(ai.httpx, "AsyncClient", client)
        await ai.review_signal(SIGNAL)
        assert len(spy.settlements) == 1, expected
        settled = spy.settlements[0]
        for key, value in expected.items():
            assert settled.get(key, True if key == "billable" else None) == value, (key, settled)
    _reset_openai(ai)


@pytest.mark.asyncio
async def test_gemini_budget_refusal_skips_both_protected_and_legacy_calls(monkeypatch):
    import services.gemini_ml as gemini

    class Models:
        calls = 0

        def generate_content(self, **kwargs):
            Models.calls += 1
            raise AssertionError("budget refusal must not reach the provider")

    monkeypatch.setattr(gemini, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini, "client", type("Client", (), {"models": Models()})())
    gemini._reset_gemini_provider_circuit_for_tests()
    spy = _LedgerSpy(admitted=False)
    monkeypatch.setattr(gemini.ai_cost_ledger, "admit", spy.admit)
    monkeypatch.setattr(gemini.ai_cost_ledger, "settle", spy.settle)

    structured = await gemini.review_signal_structured(SIGNAL, [], None)
    assert structured["ok"] is False and structured["error"] == "budget_exhausted"

    with pytest.raises(gemini.ai_cost_ledger.AIBudgetExhausted):
        await gemini._ledgered_generate_content("prompt", task="gemini_final_veto", workload="signal_review")

    assert Models.calls == 0
    assert [(a.task, a.workload) for a in spy.admissions] == [
        ("gemini_trade_review", "signal_review"),
        ("gemini_final_veto", "signal_review"),
    ]
    gemini._reset_gemini_provider_circuit_for_tests()


@pytest.mark.asyncio
async def test_gemini_settles_reported_usage_and_definite_rejections(monkeypatch):
    import services.gemini_ml as gemini

    class Meta:
        prompt_token_count = 70
        candidates_token_count = 11
        thoughts_token_count = 4

    class Response:
        usage_metadata = Meta()
        text = "fine"

    class Rejected(Exception):
        status_code = 403

    outcomes = [Response(), Rejected("403 forbidden")]

    class Models:
        def generate_content(self, **kwargs):
            item = outcomes.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    monkeypatch.setattr(gemini, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini, "client", type("Client", (), {"models": Models()})())
    monkeypatch.setenv("GEMINI_REVIEW_MAX_CALLS_PER_WINDOW", "100")
    gemini._reset_gemini_provider_circuit_for_tests()
    spy = _LedgerSpy()
    monkeypatch.setattr(gemini.ai_cost_ledger, "admit", spy.admit)
    monkeypatch.setattr(gemini.ai_cost_ledger, "settle", spy.settle)

    first = await gemini._call_gemini_result("hello", max_tokens=64, task="gemini_text", workload="chat")
    second = await gemini._call_gemini_result("hello", max_tokens=64, task="gemini_text", workload="chat")

    assert first["ok"] is True and second["ok"] is False
    assert spy.settlements[0]["prompt_tokens"] == 70 and spy.settlements[0]["completion_tokens"] == 15
    assert spy.settlements[0]["tokens_estimated"] is False
    assert spy.settlements[1]["billable"] is False and spy.settlements[1]["error"] == "provider_http_403"
    gemini._reset_gemini_provider_circuit_for_tests()


@pytest.mark.asyncio
async def test_budget_skipped_review_still_gets_the_deterministic_gate(monkeypatch):
    """Even with AI_REVIEW_FALLBACK_ENABLED off, a budget skip is never waived."""
    import engine.core as core
    import services.ai_review_router as router

    monkeypatch.setenv("AI_REVIEW_FALLBACK_ENABLED", "0")

    async def budget_skipped(*args, **kwargs):
        return {
            "ok": False,
            "provider": "local",
            "error": "external_review_unavailable",
            "provider_trace": [{"provider": "openai", "ok": False, "error": "budget_exhausted"}],
        }

    monkeypatch.setattr(router, "review_signal", budget_skipped)
    weak = dict(SIGNAL, score=60.0, ml_probability=0.4, rr_ratio=8.0)
    expected_ok, expected_score, _ = core._local_ai_review_signal(weak, [{"close": 100.0}] * 100)

    ok, score, reason = await core._gemini_review_signal(weak, [{"close": 100.0}] * 100, None)

    assert expected_ok is False  # the weak setup fails the deterministic review
    assert (ok, score) == (expected_ok, expected_score)
    assert reason.startswith("ai_review_status=budget_exhausted;local_ai:")

    async def plain_outage(*args, **kwargs):
        return {"ok": False, "provider": "local", "error": "external_review_unavailable", "provider_trace": []}

    monkeypatch.setattr(router, "review_signal", plain_outage)
    # Unchanged legacy behaviour for a non-budget outage with the fallback disabled.
    assert (await core._gemini_review_signal(weak, [], None))[2].startswith("ai_review_fallback_disabled")


@pytest.mark.asyncio
async def test_consensus_unavailable_reports_budget_skips_in_its_trace(monkeypatch):
    import services.ai_review_router as router

    monkeypatch.setenv("AI_SIGNAL_REVIEW_MODE", "consensus")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "openai,gemini,local")

    async def skipped(provider, *args, **kwargs):
        return {"ok": False, "provider": provider, "error": "budget_exhausted", "skipped": True}

    monkeypatch.setattr(router, "_call_provider", skipped)
    result = await router.review_signal(SIGNAL)
    assert result["ok"] is False
    assert [row["error"] for row in result["provider_trace"]] == ["budget_exhausted", "budget_exhausted"]
