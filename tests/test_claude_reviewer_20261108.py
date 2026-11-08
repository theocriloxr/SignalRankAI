"""Claude as the AI reviewer while OpenAI is unavailable (owner request, 8 Nov 2026)."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from services import ai_cost_ledger, ai_review_router, claude_ai

_SIGNAL = {"asset": "BTCUSDT", "timeframe": "1h", "direction": "long", "entry": 100.0,
           "stop_loss": 98.0, "take_profit": [104.0, 106.0], "score": 88, "strategy_name": "ADX Trend"}


class _FakeMessages:
    def __init__(self, payload, stop_reason="end_turn"):
        self.payload, self.stop_reason, self.calls = payload, stop_reason, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="msg_1", model=kwargs["model"], stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
            usage=SimpleNamespace(input_tokens=900, output_tokens=120, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0))


def _fake_client(payload, stop_reason="end_turn"):
    messages = _FakeMessages(payload, stop_reason)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages)), messages


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("AI_USAGE_LEDGER_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_REVIEW_MODEL", raising=False)
    monkeypatch.setattr(claude_ai, "_CACHE", {})
    monkeypatch.setattr(claude_ai, "_CIRCUIT_UNTIL", 0.0)
    monkeypatch.setattr(claude_ai, "_WINDOW_CALLS", 0)

    async def _admit(**kw):
        return SimpleNamespace(admitted=True)

    async def _settle(*a, **kw):
        return None

    monkeypatch.setattr(ai_cost_ledger, "admit", _admit)
    monkeypatch.setattr(ai_cost_ledger, "settle", _settle)


_APPROVE = {"approved": True, "score": 8.6, "confidence": 0.74, "risk_level": "medium",
            "summary": "Trend and volume agree.", "veto_reasons": [], "retail_trap_risk": False,
            "late_entry_risk": False, "macro_conflict": False, "volatility_risk": False,
            "data_quality_risk": False}


def test_router_fails_over_from_missing_openai_to_claude(monkeypatch):
    client, messages = _fake_client(_APPROVE)
    monkeypatch.setattr(claude_ai, "_client", client)
    monkeypatch.setenv("AI_PROVIDER_ORDER", "openai,claude,gemini,local")
    result = asyncio.run(ai_review_router.review_signal(dict(_SIGNAL), [], None))
    assert result["ok"] and result["provider"] == "claude" and result["data"]["score"] == 8.6
    trace = {row["provider"]: row for row in result["provider_trace"]}
    assert trace["openai"]["ok"] is False and trace["claude"]["ok"] is True
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["effort"] == "low"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert "minimum" not in json.dumps(call["output_config"]["format"]["schema"])
    # The reviewer sees the same untrusted-data instructions as every other provider.
    from services.openai_ai import SIGNAL_REVIEW_SYSTEM
    assert call["system"] == SIGNAL_REVIEW_SYSTEM
    assert json.loads(call["messages"][0]["content"])["signal"]["asset"] == "BTCUSDT"


def test_refusal_and_bad_json_fall_through_to_local(monkeypatch):
    client, _ = _fake_client(_APPROVE, stop_reason="refusal")
    monkeypatch.setattr(claude_ai, "_client", client)
    monkeypatch.setenv("AI_PROVIDER_ORDER", "claude,local")
    result = asyncio.run(ai_review_router.review_signal(dict(_SIGNAL), [], None))
    assert result["ok"] is False and result["provider_trace"][0]["error"] == "refusal"


def test_hourly_cap_and_disable(monkeypatch):
    client, messages = _fake_client(_APPROVE)
    monkeypatch.setattr(claude_ai, "_client", client)
    monkeypatch.setenv("CLAUDE_REVIEW_MAX_CALLS_PER_HOUR", "1")
    first = asyncio.run(claude_ai.review_signal(dict(_SIGNAL)))
    other = dict(_SIGNAL, asset="ETHUSDT")
    second = asyncio.run(claude_ai.review_signal(other))
    assert first["ok"] and second["error"] == "budget_hourly_calls" and len(messages.calls) == 1
    cached = asyncio.run(claude_ai.review_signal(dict(_SIGNAL)))
    assert cached["ok"] and cached["cache_hit"]
    monkeypatch.setenv("CLAUDE_AI_ENABLED", "false")
    assert not claude_ai.claude_available()


def test_direction_arbitration_via_claude(monkeypatch):
    client, messages = _fake_client({"winner": "short", "confidence": 0.81, "reason": "HTF bearish."})
    monkeypatch.setattr(claude_ai, "_client", client)
    monkeypatch.setenv("AI_PROVIDER_ORDER", "claude,local")
    out = asyncio.run(ai_review_router.choose_direction("BTCUSDT", "1h", [{"score": 70}], [{"score": 82}]))
    assert out.get("winner") == "short" or out.get("data", {}).get("winner") == "short", out


def test_claude_pricing_and_budget_scope():
    assert ai_cost_ledger.price_for("claude", "claude-opus-5-5", env={})[:2] == (4.0, 20.0)
    limits = ai_cost_ledger.parse_budget_limits({"AI_BUDGET_CLAUDE_DAILY_USD": "3"})
    assert any(limit.kind == "provider" and limit.value == "claude" for limit in limits)
    assert ai_cost_ledger.claude_usage_tokens({"input_tokens": 10, "cache_read_input_tokens": 5,
                                               "output_tokens": 7}) == (15, 7)
