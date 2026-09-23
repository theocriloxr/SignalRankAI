from __future__ import annotations

import pytest


def _signal() -> dict:
    return {
        "asset": "BTCUSDT",
        "asset_class": "crypto",
        "timeframe": "1h",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 98.0,
        "take_profit": [104.0],
        "score": 92.0,
        "confidence": 0.86,
        "rr_ratio": 2.0,
        "ml_probability": 0.74,
    }


def _provider_result(provider: str, *, score: float, confidence: float, approved: bool, model: str) -> dict:
    return {
        "ok": True,
        "provider": provider,
        "model": model,
        "data": {
            "approved": approved,
            "score": score,
            "confidence": confidence,
            "risk_level": "low" if approved else "high",
            "summary": f"{provider} structured review",
            "veto_reasons": [] if approved else ["context_conflict"],
            "retail_trap_risk": False,
            "late_entry_risk": False,
            "macro_conflict": not approved,
            "volatility_risk": False,
            "data_quality_risk": False,
        },
        "latency_ms": 12.0,
        "usage": {"input_tokens": 10, "output_tokens": 6},
        "input_hash": f"{provider}-hash",
    }


@pytest.mark.asyncio
async def test_router_failover_uses_gemini_after_openai_degrades(monkeypatch):
    import services.ai_review_router as router
    import services.openai_ai as openai_ai
    import services.gemini_ml as gemini

    monkeypatch.setenv("AI_SIGNAL_REVIEW_MODE", "failover")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "openai,gemini,local")
    monkeypatch.setattr(openai_ai, "openai_available", lambda: True)
    monkeypatch.setattr(openai_ai, "provider_order", lambda: ("openai", "gemini", "local"))
    monkeypatch.setattr(gemini, "gemini_available", lambda: True)

    async def openai_degraded(*args, **kwargs):
        return {"ok": False, "provider": "openai", "error": "timeout"}

    async def gemini_ok(*args, **kwargs):
        return _provider_result("gemini", score=8.7, confidence=0.78, approved=True, model="gemini-test")

    monkeypatch.setattr(openai_ai, "review_signal", openai_degraded)
    monkeypatch.setattr(gemini, "review_signal_structured", gemini_ok)

    result = await router.review_signal(_signal(), [{"close": 100.0}], 0.0)

    assert result["ok"] is True
    assert result["provider"] == "gemini"
    assert result["data"]["approved"] is True
    assert result["data"]["score"] == pytest.approx(8.7)
    assert result["provider_trace"][0] == {"provider": "openai", "ok": False, "error": "timeout"}
    assert result["provider_trace"][1]["provider"] == "gemini"
    assert result["provider_trace"][1]["ok"] is True


@pytest.mark.asyncio
async def test_router_consensus_requires_agreement_and_bounded_score_gap(monkeypatch):
    import services.ai_review_router as router
    import services.openai_ai as openai_ai
    import services.gemini_ml as gemini

    monkeypatch.setenv("AI_SIGNAL_REVIEW_MODE", "consensus")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "openai,gemini,local")
    monkeypatch.setenv("AI_CONSENSUS_MIN", "0.70")
    monkeypatch.setenv("AI_DISAGREEMENT_MAX", "0.20")
    monkeypatch.setattr(openai_ai, "openai_available", lambda: True)
    monkeypatch.setattr(openai_ai, "provider_order", lambda: ("openai", "gemini", "local"))
    monkeypatch.setattr(gemini, "gemini_available", lambda: True)

    async def openai_ok(*args, **kwargs):
        return _provider_result("openai", score=8.8, confidence=0.82, approved=True, model="gpt-test")

    async def gemini_ok(*args, **kwargs):
        return _provider_result("gemini", score=8.4, confidence=0.76, approved=True, model="gemini-test")

    monkeypatch.setattr(openai_ai, "review_signal", openai_ok)
    monkeypatch.setattr(gemini, "review_signal_structured", gemini_ok)

    result = await router.review_signal(_signal(), [{"close": 100.0}], 0.0)

    assert result["ok"] is True
    assert result["provider"] == "consensus"
    assert result["data"]["approved"] is True
    assert result["data"]["score"] == pytest.approx(8.6)
    assert result["data"]["confidence"] == pytest.approx(0.79)
    assert result["data"]["provider_disagreement"] == pytest.approx(0.04)
    assert result["data"]["decision_disagreement"] is False
    assert len(result["provider_results"]) == 2


@pytest.mark.asyncio
async def test_router_consensus_blocks_when_providers_disagree_on_decision(monkeypatch):
    import services.ai_review_router as router
    import services.openai_ai as openai_ai
    import services.gemini_ml as gemini

    monkeypatch.setenv("AI_SIGNAL_REVIEW_MODE", "consensus")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "openai,gemini,local")
    monkeypatch.setenv("AI_CONSENSUS_MIN", "0.70")
    monkeypatch.setenv("AI_DISAGREEMENT_MAX", "0.20")
    monkeypatch.setattr(openai_ai, "openai_available", lambda: True)
    monkeypatch.setattr(openai_ai, "provider_order", lambda: ("openai", "gemini", "local"))
    monkeypatch.setattr(gemini, "gemini_available", lambda: True)

    async def openai_ok(*args, **kwargs):
        return _provider_result("openai", score=8.9, confidence=0.84, approved=True, model="gpt-test")

    async def gemini_veto(*args, **kwargs):
        return _provider_result("gemini", score=8.5, confidence=0.80, approved=False, model="gemini-test")

    monkeypatch.setattr(openai_ai, "review_signal", openai_ok)
    monkeypatch.setattr(gemini, "review_signal_structured", gemini_veto)

    result = await router.review_signal(_signal(), [{"close": 100.0}], 0.0)

    assert result["ok"] is True
    assert result["provider"] == "consensus"
    assert result["data"]["approved"] is False
    assert result["data"]["decision_disagreement"] is True


@pytest.mark.asyncio
async def test_router_blocks_invalid_structure_before_any_external_call(monkeypatch):
    import services.ai_review_router as router
    import services.openai_ai as openai_ai
    import services.gemini_ml as gemini

    calls = {"openai": 0, "gemini": 0}
    monkeypatch.setenv("AI_SIGNAL_REVIEW_MODE", "consensus")
    monkeypatch.setattr(openai_ai, "openai_available", lambda: True)
    monkeypatch.setattr(openai_ai, "provider_order", lambda: ("openai", "gemini", "local"))
    monkeypatch.setattr(gemini, "gemini_available", lambda: True)

    async def openai_call(*args, **kwargs):
        calls["openai"] += 1
        return _provider_result("openai", score=9.0, confidence=0.9, approved=True, model="gpt-test")

    async def gemini_call(*args, **kwargs):
        calls["gemini"] += 1
        return _provider_result("gemini", score=9.0, confidence=0.9, approved=True, model="gemini-test")

    monkeypatch.setattr(openai_ai, "review_signal", openai_call)
    monkeypatch.setattr(gemini, "review_signal_structured", gemini_call)

    invalid = _signal()
    invalid["stop_loss"] = 101.0
    result = await router.review_signal(invalid, [{"close": 100.0}], 0.0)

    assert result["ok"] is True
    assert result["provider"] == "local"
    assert result["data"]["approved"] is False
    assert result["data"]["risk_level"] == "critical"
    assert calls == {"openai": 0, "gemini": 0}


@pytest.mark.asyncio
async def test_engine_persists_provider_neutral_review_provenance(monkeypatch):
    import engine.core as core
    import services.ai_review_router as router

    async def consensus(*args, **kwargs):
        return {
            "ok": True,
            "provider": "consensus",
            "model": "gpt-test+gemini-test",
            "data": {
                "approved": True,
                "score": 8.7,
                "confidence": 0.81,
                "risk_level": "low",
                "summary": "both reviewers agree",
                "veto_reasons": [],
                "provider_disagreement": 0.03,
                "decision_disagreement": False,
            },
            "latency_ms": 15.5,
            "usage": {"input_tokens": 12, "output_tokens": 8},
            "provider_results": [
                {"provider": "openai", "model": "gpt-test", "approved": True, "score": 8.8, "confidence": 0.82, "latency_ms": 12.0},
                {"provider": "gemini", "model": "gemini-test", "approved": True, "score": 8.6, "confidence": 0.80, "latency_ms": 15.5},
            ],
        }

    monkeypatch.setattr(router, "review_signal", consensus)
    signal = _signal()
    ok, score, reason = await core._gemini_review_signal(signal, [{"close": 100.0}] * 40, 0.0)

    assert ok is True
    assert score == pytest.approx(8.7)
    assert signal["ai_review_provider"] == "consensus"
    assert signal["ai_review_model"] == "gpt-test+gemini-test"
    assert signal["ai_review_confidence"] == pytest.approx(0.81)
    assert signal["ai_review_disagreement"] == pytest.approx(0.03)
    assert signal["ai_review_usage"]["input_tokens"] == 12
    assert len(signal["ai_review_provider_results"]) == 2
    assert signal["gemini_review_score"] == pytest.approx(8.7)
    assert "provider=consensus" in reason
