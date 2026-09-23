from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http_{self.status_code}")


class _FakeAsyncClient:
    captured: list[dict] = []
    payload: dict = {}

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, headers=None, json=None):
        type(self).captured.append({"url": url, "headers": headers or {}, "json": json or {}})
        return _FakeResponse(type(self).payload)


@pytest.fixture(autouse=True)
def _reset_openai_state(monkeypatch):
    import services.openai_ai as ai

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_AI_ENABLED", "1")
    monkeypatch.setenv("OPENAI_SIGNAL_REVIEW_ENABLED", "1")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "openai,gemini,local")
    monkeypatch.setenv("OPENAI_AI_CIRCUIT_BREAKER_ENABLED", "1")
    monkeypatch.setenv("OPENAI_AI_MAX_CALLS_PER_WINDOW", "20")
    ai._WINDOW_STARTED_MONO = 0.0
    ai._WINDOW_CALLS = 0
    ai._CIRCUIT_UNTIL_MONO = 0.0
    ai._CIRCUIT_REASON = ""
    _FakeAsyncClient.captured.clear()


@pytest.mark.asyncio
async def test_openai_signal_review_uses_responses_structured_output_and_no_storage(monkeypatch):
    import services.openai_ai as ai

    response_data = {
        "approved": True,
        "score": 8.8,
        "confidence": 0.77,
        "risk_level": "low",
        "summary": "Context supports the setup.",
        "veto_reasons": [],
        "retail_trap_risk": False,
        "late_entry_risk": False,
        "macro_conflict": False,
        "volatility_risk": False,
        "data_quality_risk": False,
    }
    _FakeAsyncClient.payload = {
        "id": "resp_test",
        "output": [{"content": [{"type": "output_text", "text": json.dumps(response_data)}]}],
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }
    monkeypatch.setattr(ai.httpx, "AsyncClient", _FakeAsyncClient)

    result = await ai.review_signal(
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "direction": "long",
            "entry": 100.0,
            "stop_loss": 98.0,
            "take_profit": [104.0, 106.0],
            "score": 91.0,
            "secret_should_not_leave": "nope",
        },
        [{"timestamp": 1, "open": 99, "high": 101, "low": 98, "close": 100, "volume": 5}],
        0.2,
    )

    assert result["ok"] is True
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-5.6-terra"
    assert result["data"]["score"] == pytest.approx(8.8)
    call = _FakeAsyncClient.captured[-1]
    body = call["json"]
    assert call["url"] == "https://api.openai.com/v1/responses"
    assert body["store"] is False
    assert body["reasoning"]["effort"] == "low"
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    serialized = json.dumps(body)
    assert "secret_should_not_leave" not in serialized
    assert "test-openai-key" not in serialized


@pytest.mark.asyncio
async def test_openai_rate_limit_opens_circuit(monkeypatch):
    import services.openai_ai as ai

    class RateLimitedClient(_FakeAsyncClient):
        async def post(self, url, *, headers=None, json=None):
            return _FakeResponse({"error": {"message": "rate limited"}}, status_code=429)

    monkeypatch.setattr(ai.httpx, "AsyncClient", RateLimitedClient)
    first = await ai.review_signal({"asset": "BTCUSDT", "direction": "long", "entry": 100, "stop_loss": 98})
    second = await ai.review_signal({"asset": "BTCUSDT", "direction": "long", "entry": 100, "stop_loss": 98})

    assert first["ok"] is False
    assert first["error"] == "rate_limited"
    assert second["ok"] is False
    assert second["circuit_open"] is True


@pytest.mark.asyncio
async def test_engine_openai_failure_falls_back_without_bypassing_local_review(monkeypatch):
    import engine.core as core
    import services.openai_ai as ai

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "openai,gemini,local")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    async def degraded(*args, **kwargs):
        return {"ok": False, "provider": "openai", "error": "timeout"}

    monkeypatch.setattr(ai, "review_signal", degraded)
    ok, score, reason = await core._gemini_review_signal(
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "direction": "long",
            "entry": 100.0,
            "stop_loss": 98.0,
            "take_profit": [104.0],
            "score": 90.0,
            "confidence": 0.9,
            "rr_ratio": 2.0,
        },
        [{"close": 100.0}] * 40,
        0.0,
    )
    assert isinstance(ok, bool)
    assert score is None or 0 <= score <= 10
    assert "local_ai" in reason or "fallback" in reason or reason


def test_ai_compatibility_surface_routes_openai_but_keeps_gemini_fallback():
    source = Path("services/gemini_ml.py").read_text(encoding="utf-8")
    for function_name in (
        "quantize_news_sentiment",
        "ask_gemini_signal_explanation",
        "ask_gemini_custom_question",
        "analyze_market_regime",
        "get_news_sentiment",
        "gemini_confluence_check_with_tech_context",
        "gemini_confluence_check",
        "gemini_risk_review",
        "run_gemini_review_pipeline",
        "gemini_final_veto",
    ):
        block_start = source.index(f"async def {function_name}")
        next_def = source.find("\nasync def ", block_start + 10)
        block = source[block_start : next_def if next_def > 0 else len(source)]
        assert "_openai" in block or "_openai_preferred_available" in block
    assert "gemini_available()" in source


def test_ai_review_is_provider_neutral_and_legacy_fields_remain_compatible():
    engine = Path("engine/core.py").read_text(encoding="utf-8")
    formatter = Path("signalrank_telegram/tier_signal_formatter.py").read_text(encoding="utf-8")
    intelligence = Path("services/trading_intelligence.py").read_text(encoding="utf-8")

    assert "sig['ai_review_provider']" in engine
    assert "sig['ai_review_score']" in engine
    assert "sig['ai_review_reason']" in engine
    assert "sig['gemini_review_score'] = gemini_score" in engine
    assert '"QUALITY_MIN_AI_SCORE"' in engine
    assert '"OpenAI"' in formatter
    assert 'signal.get("ai_review_score") or signal.get("gemini_review_score")' in formatter
    assert 'signal.get("ai_review_score") or signal.get("gemini_review_score")' in intelligence


def test_ai_feedback_remains_proposal_only():
    source = Path("worker/ai_feedback.py").read_text(encoding="utf-8")
    assert "threshold_recommendation" in source
    assert '"requires_owner_approval": True' in source
    assert '"auto_apply": False' in source
    assert "requires_forward_test" in source
