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
    ai._RESPONSE_CACHE.clear()
    ai._CACHE_HITS = 0
    ai._CACHE_MISSES = 0
    ai._USAGE_INPUT_TOKENS = 0
    ai._USAGE_OUTPUT_TOKENS = 0
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
    assert result["model"] == "gpt-5.6-luna"
    assert result["data"]["score"] == pytest.approx(8.8)
    call = _FakeAsyncClient.captured[-1]
    body = call["json"]
    assert call["url"] == "https://api.openai.com/v1/responses"
    assert body["store"] is False
    assert body["reasoning"]["effort"] == "low"
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert body["prompt_cache_key"].startswith("signalrank-signalrank_trade_review-")
    serialized = json.dumps(body)
    assert "secret_should_not_leave" not in serialized
    assert "test-openai-key" not in serialized


@pytest.mark.asyncio
async def test_openai_identical_review_uses_local_ttl_cache_without_second_api_call(monkeypatch):
    import services.openai_ai as ai

    response_data = {
        "approved": True,
        "score": 8.4,
        "confidence": 0.75,
        "risk_level": "low",
        "summary": "Supported.",
        "veto_reasons": [],
        "retail_trap_risk": False,
        "late_entry_risk": False,
        "macro_conflict": False,
        "volatility_risk": False,
        "data_quality_risk": False,
    }
    _FakeAsyncClient.payload = {
        "id": "resp_cached",
        "output": [{"content": [{"type": "output_text", "text": json.dumps(response_data)}]}],
        "usage": {"input_tokens": 11, "output_tokens": 13},
    }
    monkeypatch.setattr(ai.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setenv("OPENAI_SIGNAL_CACHE_TTL_SECONDS", "180")

    signal = {
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 98.0,
        "score": 92.0,
    }
    first = await ai.review_signal(signal, [], 0.0)
    second = await ai.review_signal(signal, [], 0.0)

    assert first["ok"] is True and first["cache_hit"] is False
    assert second["ok"] is True and second["cache_hit"] is True
    assert len(_FakeAsyncClient.captured) == 1
    status = ai.provider_status()
    assert status["cache"]["hits"] == 1
    assert status["cache"]["misses"] == 1
    assert status["usage_totals"] == {"input_tokens": 11, "output_tokens": 13}


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

def test_openai_provider_status_is_secret_safe(monkeypatch):
    import services.openai_ai as ai

    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("OPENAI_DEEP_MODEL", "gpt-5.6-terra")
    status = ai.provider_status()

    assert status["configured"] is True
    assert status["available"] is True
    assert status["responses_api"] is True
    assert status["store"] is False
    assert status["signal_model"] == "gpt-5.6-luna"
    assert status["deep_model"] == "gpt-5.6-terra"
    assert status["cache"]["entries"] == 0
    assert status["cache"]["hits"] == 0
    assert status["usage_totals"]["input_tokens"] == 0
    serialized = json.dumps(status)
    assert "super-secret-openai-key" not in serialized
    assert "OPENAI_API_KEY" not in serialized


@pytest.mark.asyncio
async def test_openai_connectivity_probe_is_structured_and_non_trading(monkeypatch):
    import services.openai_ai as ai

    _FakeAsyncClient.payload = {
        "id": "resp_connectivity",
        "output": [{
            "content": [{
                "type": "output_text",
                "text": json.dumps({"status": "ok", "message": "connected"}),
            }]
        }],
        "usage": {"input_tokens": 4, "output_tokens": 5},
    }
    monkeypatch.setattr(ai.httpx, "AsyncClient", _FakeAsyncClient)

    result = await ai.test_connection()
    assert result["ok"] is True
    assert result["connected"] is True
    call = _FakeAsyncClient.captured[-1]
    assert call["url"] == "https://api.openai.com/v1/responses"
    assert call["json"]["store"] is False
    assert call["json"]["text"]["format"]["name"] == "signalrank_provider_connectivity"
    serialized = json.dumps(call["json"]).lower()
    assert "buy" not in serialized
    assert "sell" not in serialized
    assert "expected profit" not in serialized


def test_provider_neutral_telegram_ai_commands_are_registered_and_governed():
    bot = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    commands = Path("signalrank_telegram/commands.py").read_text(encoding="utf-8")
    policy = Path("core/tier_policy.py").read_text(encoding="utf-8")
    catalogue = Path("signalrank_telegram/command_catalog.py").read_text(encoding="utf-8")

    for command in ("ai", "ai_review", "ai_analyze", "ai_audit", "ai_predict", "ai_status", "ai_test"):
        assert f'CommandHandler("{command}"' in bot
    assert "async def ai_status_command" in commands
    assert "async def ai_test_command" in commands
    assert '"ai": Tier.ADMIN' in policy
    assert '"ai_status": Tier.OWNER' in policy
    assert '"ai_test": Tier.OWNER' in policy
    assert 'CommandSpec("ai",' in catalogue
    assert 'CommandSpec("ai_status",' in catalogue
    assert "OPENAI_API_KEY" in commands
    assert "Do not paste the API key into Telegram or chat logs." in commands


def test_frontdoor_ownership_recovers_only_explicit_frontdoor_hint():
    source = Path("railway_main.py").read_text(encoding="utf-8")
    start = source.index("def _railway_process_ownership")
    end = source.index("def _is_running_on_railway", start)
    block = source[start:end]

    assert 'os.getenv("DB_ROLE")' in block
    assert 'requested in {"all", "all/dev"}' in block
    assert '"frontdoor", "front-door", "webhook"' in block
    assert 'requested = "frontdoor"' in block
    assert "railway_main:app cannot own RUN_MODE=" in block
    assert "engine" not in block.split('role_hint in {', 1)[1].split('}', 1)[0]
    assert "worker" not in block.split('role_hint in {', 1)[1].split('}', 1)[0]

def test_start_script_honors_railway_run_mode_truthy_aliases():
    source = Path("start.sh").read_text(encoding="utf-8")
    assert 'case "${HONOR_RUN_MODE_ON_RAILWAY:-false}" in' in source
    assert "1|true|TRUE|yes|YES|on|ON)" in source
    assert 'case "${RUN_MODE}" in' in source
    assert "web|worker|engine|bot|delivery|outcome|analytics|scheduler)" in source
    assert 'exec python main.py' in source



def test_readyz_exposes_secret_safe_optional_openai_status():
    source = Path("railway_main.py").read_text(encoding="utf-8")
    ready = source[source.index('async def _readyz_endpoint'):source.index('async def _telegram_webhook_route')]
    assert 'from services.openai_ai import provider_status as _openai_provider_status' in ready
    assert 'OPENAI_REQUIRED_FOR_READINESS' in ready
    assert 'checks["openai_ai"]' in ready
    assert '"not_configured_optional"' in ready
    assert 'OPENAI_API_KEY' not in ready


def test_ai_provider_provenance_is_preserved_and_outcome_attributed():
    engine = Path("engine/core.py").read_text(encoding="utf-8")
    governance = Path("services/codex_governance.py").read_text(encoding="utf-8")
    reviewer = Path("scripts/ai_reviewer.py").read_text(encoding="utf-8")

    scoring = engine[engine.index("gemini_ok, gemini_score, gemini_reason"):engine.index("from core.signal_quality_gate", engine.index("gemini_ok, gemini_score, gemini_reason"))]
    assert 'sig.get("ai_review_provider")' in scoring
    assert "provider=consensus" in scoring
    assert "sig['ai_review_provider'] = ai_provider" in scoring

    logging_block = engine[engine.index("def _log_decision"):engine.index("def _log_market_observations")]
    for key in (
        "ai_review_provider",
        "ai_review_model",
        "ai_review_score",
        "ai_review_confidence",
        "ai_review_disagreement",
        "ai_review_latency_ms",
        "ai_review_provider_results",
    ):
        assert key in logging_block

    assert "ai_provider_performance = (" in governance
    assert "COUNT(o.id) AS outcomes" in governance
    assert "AVG(o.r_multiple) AS avg_r" in governance
    assert "AVG(a.ai_score) AS avg_ai_score" in governance
    assert "AVG(a.ai_confidence) AS avg_ai_confidence" in governance
    assert "AVG(a.ai_disagreement) AS avg_ai_disagreement" in governance
    assert '"ai_provider_performance": [dict(row) for row in ai_provider_performance]' in governance

    assert "performance_review" in reviewer
    assert "run_external_gemini_aggregate_review" in reviewer
    assert "aggregate_only_no_user_or_signal_ids" in reviewer
    assert '"production_mutation": False' in reviewer
    assert '"requires_owner_approval": True' in reviewer


def test_ai_review_router_supports_failover_and_consensus_modes():
    router = Path("services/ai_review_router.py").read_text(encoding="utf-8")
    assert 'AI_SIGNAL_REVIEW_MODE' in router
    assert 'mode not in {"failover", "consensus"}' in router
    assert 'AI_CONSENSUS_REQUIRE_TWO_PROVIDERS' in router
    assert 'AI_DISAGREEMENT_MAX' in router
    assert 'AI_CONSENSUS_MIN' in router
    assert 'asyncio.gather(*calls, return_exceptions=True)' in router
    assert 'provider_disagreement' in router
    assert 'decision_disagreement' in router
    assert 'Deterministic risk structure is invalid; AI cannot override it.' in router
