"""Provider-neutral AI review routing for SignalRankAI.

OpenAI is the preferred external reviewer when configured. Gemini can act as an
independent secondary reviewer or failover. Deterministic trading/risk/data
controls remain authoritative and are never weakened by AI output.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Sequence

logger = logging.getLogger("AIReviewRouter")


@dataclass(frozen=True, slots=True)
class ReviewResult:
    reviewer: str
    model: str
    prompt_version: str
    status: str
    summary: str
    input_hash: str
    latency_ms: float
    fallback_used: bool = False
    error: str | None = None
    approved: bool | None = None
    score: float | None = None
    confidence: float | None = None
    risk_level: str | None = None
    disagreement: float | None = None
    provider_results: tuple[Mapping[str, Any], ...] = ()
    usage: Mapping[str, Any] | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float = 0.0, maximum: float = 3600.0) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        value = float(default)
    return max(minimum, min(maximum, value))


def _fingerprint(signal: Mapping[str, Any]) -> str:
    safe = {
        key: signal.get(key)
        for key in (
            "asset", "asset_class", "timeframe", "direction", "strategy_name",
            "entry", "stop_loss", "take_profit", "targets", "score",
            "confidence", "rr_ratio", "ml_probability", "regime", "session",
        )
        if signal.get(key) is not None
    }
    return hashlib.sha256(repr(sorted(safe.items())).encode()).hexdigest()[:24]


def _local_review(signal: Mapping[str, Any]) -> ReviewResult:
    started = time.perf_counter()
    asset = str(signal.get("asset") or "unknown")
    direction = str(signal.get("direction") or "unknown").upper()
    summary = (
        f"{asset} {direction}: deterministic review requires fresh quote, "
        "ordered stop/targets, and explicit risk limits."
    )
    return ReviewResult(
        "local",
        "deterministic-v1",
        "local-review-v1",
        "ok",
        summary,
        _fingerprint(signal),
        (time.perf_counter() - started) * 1000,
        fallback_used=True,
    )


def _invalid_structure(signal: Mapping[str, Any]) -> bool:
    try:
        entry = float(signal.get("entry") or 0)
        stop = float(signal.get("stop_loss") or signal.get("stop") or 0)
    except (TypeError, ValueError):
        return True
    direction = str(signal.get("direction") or "").lower()
    if entry <= 0 or stop <= 0:
        return True
    if direction in {"long", "buy"} and stop >= entry:
        return True
    if direction in {"short", "sell"} and stop <= entry:
        return True
    return direction not in {"long", "buy", "short", "sell"}


def _provider_order() -> tuple[str, ...]:
    try:
        from services.openai_ai import provider_order

        return tuple(provider_order())
    except Exception:
        raw = str(os.getenv("AI_PROVIDER_ORDER") or "openai,gemini,local")
        order: list[str] = []
        for item in raw.split(","):
            value = item.strip().lower()
            if value in {"openai", "gemini", "local"} and value not in order:
                order.append(value)
        if "local" not in order:
            order.append("local")
        return tuple(order)


async def _review_openai(
    signal: Mapping[str, Any],
    candles: Sequence[Mapping[str, Any]] | None,
    news_sentiment: float | None,
) -> Mapping[str, Any]:
    from services.openai_ai import openai_available, review_signal

    if not openai_available():
        return {"ok": False, "provider": "openai", "error": "not_available"}
    return await review_signal(signal, candles, news_sentiment)


async def _review_gemini(
    signal: Mapping[str, Any],
    candles: Sequence[Mapping[str, Any]] | None,
    news_sentiment: float | None,
) -> Mapping[str, Any]:
    from services.gemini_ml import gemini_available, review_signal_structured

    if not gemini_available():
        return {"ok": False, "provider": "gemini", "error": "not_available"}
    return await review_signal_structured(signal, candles, news_sentiment)


async def _call_provider(
    provider: str,
    signal: Mapping[str, Any],
    candles: Sequence[Mapping[str, Any]] | None,
    news_sentiment: float | None,
) -> Mapping[str, Any]:
    if provider == "openai":
        return await _review_openai(signal, candles, news_sentiment)
    if provider == "gemini":
        return await _review_gemini(signal, candles, news_sentiment)
    return {"ok": False, "provider": provider, "error": "local_fallback"}


def _normalize(result: Mapping[str, Any]) -> dict[str, Any] | None:
    if not bool(result.get("ok")):
        return None
    data = result.get("data")
    if not isinstance(data, Mapping):
        return None
    try:
        score = max(0.0, min(10.0, float(data.get("score"))))
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        return None
    return {
        "provider": str(result.get("provider") or "unknown"),
        "model": str(result.get("model") or ""),
        "approved": bool(data.get("approved")),
        "score": score,
        "confidence": confidence,
        "risk_level": str(data.get("risk_level") or "unknown").lower(),
        "summary": " ".join(str(data.get("summary") or "").split())[:500],
        "veto_reasons": [str(x)[:220] for x in list(data.get("veto_reasons") or [])[:8]],
        "latency_ms": float(result.get("latency_ms") or 0.0),
        "usage": dict(result.get("usage") or {}) if isinstance(result.get("usage"), Mapping) else {},
        "response_id": str(result.get("response_id") or "")[:128],
        "input_hash": str(result.get("input_hash") or "")[:64],
    }


def _consensus_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(row["score"]) for row in results]
    confidences = [float(row["confidence"]) for row in results]
    average_score = sum(scores) / max(1, len(scores))
    average_confidence = sum(confidences) / max(1, len(confidences))
    disagreement = 0.0 if len(scores) < 2 else (max(scores) - min(scores)) / 10.0
    decision_disagreement = len({bool(row["approved"]) for row in results}) > 1
    max_disagreement = _env_float("AI_DISAGREEMENT_MAX", 0.20, minimum=0.0, maximum=1.0)
    min_confidence = _env_float("AI_CONSENSUS_MIN", 0.70, minimum=0.0, maximum=1.0)
    approved = (
        all(bool(row["approved"]) for row in results)
        and not decision_disagreement
        and disagreement <= max_disagreement
        and average_confidence >= min_confidence
    )
    summary = " | ".join(
        f"{row['provider']}:{row['score']:.1f}/10 {row['summary']}" for row in results
    )[:900]
    return {
        "ok": True,
        "provider": "consensus",
        "model": "+".join(str(row.get("model") or row["provider"]) for row in results),
        "data": {
            "approved": approved,
            "score": round(average_score, 3),
            "confidence": round(average_confidence, 4),
            "risk_level": "high" if decision_disagreement or disagreement > max_disagreement else max(
                (str(row.get("risk_level") or "unknown") for row in results),
                key=lambda value: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(value, 0),
            ),
            "summary": summary,
            "veto_reasons": [
                reason
                for row in results
                for reason in list(row.get("veto_reasons") or [])
            ][:12],
            "provider_disagreement": round(disagreement, 4),
            "decision_disagreement": decision_disagreement,
        },
        "provider_results": results,
        "latency_ms": max((float(row.get("latency_ms") or 0.0) for row in results), default=0.0),
    }


async def review_signal(
    signal: Mapping[str, Any],
    candles: Sequence[Mapping[str, Any]] | None = None,
    news_sentiment: float | None = None,
) -> dict[str, Any]:
    """Review a signal with ordered failover or independent provider consensus.

    This function is advisory. The engine still applies deterministic structure,
    market-data freshness, exposure, risk and execution controls independently.
    """
    if _invalid_structure(signal):
        local = _local_review(signal)
        return {
            "ok": True,
            "provider": "local",
            "model": local.model,
            "data": {
                "approved": False,
                "score": 0.0,
                "confidence": 1.0,
                "risk_level": "critical",
                "summary": "Deterministic risk structure is invalid; AI cannot override it.",
                "veto_reasons": ["invalid_deterministic_risk_structure"],
            },
            "fallback_used": True,
            "input_hash": local.input_hash,
            "latency_ms": local.latency_ms,
        }

    order = _provider_order()
    external = [name for name in order if name in {"openai", "gemini"}]
    mode = str(os.getenv("AI_SIGNAL_REVIEW_MODE") or "failover").strip().lower()
    if mode not in {"failover", "consensus"}:
        mode = "failover"

    if mode == "consensus" and len(external) >= 2:
        timeout = _env_float("AI_SIGNAL_REVIEW_SYNC_TIMEOUT_SEC", 7.0, minimum=1.0, maximum=60.0)
        calls = [
            asyncio.create_task(_call_provider(name, signal, candles, news_sentiment), name=f"ai-review-{name}")
            for name in external
        ]
        try:
            raw_results = await asyncio.wait_for(asyncio.gather(*calls, return_exceptions=True), timeout=timeout)
        except asyncio.TimeoutError:
            raw_results = []
            for task in calls:
                task.cancel()
        normalized: list[dict[str, Any]] = []
        for item in raw_results:
            if isinstance(item, Exception):
                continue
            row = _normalize(item)
            if row is not None:
                normalized.append(row)
        require_two = _env_bool("AI_CONSENSUS_REQUIRE_TWO_PROVIDERS", False)
        if len(normalized) >= 2:
            return _consensus_result(normalized)
        if len(normalized) == 1 and not require_two:
            single = dict(normalized[0])
            return {
                "ok": True,
                "provider": single["provider"],
                "model": single["model"],
                "data": {
                    "approved": single["approved"],
                    "score": single["score"],
                    "confidence": single["confidence"],
                    "risk_level": single["risk_level"],
                    "summary": single["summary"],
                    "veto_reasons": single["veto_reasons"],
                    "provider_disagreement": 0.0,
                    "decision_disagreement": False,
                },
                "provider_results": normalized,
                "fallback_used": True,
                "latency_ms": single["latency_ms"],
                "usage": single["usage"],
                "input_hash": single["input_hash"],
            }
        return {"ok": False, "provider": "consensus", "error": "external_consensus_unavailable"}

    provider_trace: list[dict[str, Any]] = []
    for provider in external:
        try:
            raw = await _call_provider(provider, signal, candles, news_sentiment)
        except Exception as exc:
            raw = {"ok": False, "provider": provider, "error": type(exc).__name__}
        row = _normalize(raw)
        provider_trace.append(
            {
                "provider": provider,
                "ok": row is not None,
                "error": None if row is not None else str(raw.get("error") or "invalid_response")[:120],
            }
        )
        if row is None:
            continue
        return {
            "ok": True,
            "provider": row["provider"],
            "model": row["model"],
            "data": {
                "approved": row["approved"],
                "score": row["score"],
                "confidence": row["confidence"],
                "risk_level": row["risk_level"],
                "summary": row["summary"],
                "veto_reasons": row["veto_reasons"],
                "provider_disagreement": 0.0,
                "decision_disagreement": False,
            },
            "provider_results": [row],
            "provider_trace": provider_trace,
            "latency_ms": row["latency_ms"],
            "usage": row["usage"],
            "input_hash": row["input_hash"],
        }
    return {
        "ok": False,
        "provider": "local",
        "error": "external_review_unavailable",
        "provider_trace": provider_trace,
        "fallback_used": True,
    }


class AIReviewRouter:
    """Compatibility router for call sites that inject custom reviewers."""

    def __init__(
        self,
        reviewers: Mapping[str, Callable[[Mapping[str, Any]], Awaitable[ReviewResult]]] | None = None,
    ) -> None:
        self.reviewers = dict(reviewers or {})

    async def review(self, signal: Mapping[str, Any], *, preferred: str = "openai") -> ReviewResult:
        local = _local_review(signal)
        if _invalid_structure(signal):
            return ReviewResult(
                local.reviewer,
                local.model,
                local.prompt_version,
                "blocked",
                "Deterministic risk structure is invalid; AI cannot override it.",
                local.input_hash,
                local.latency_ms,
                approved=False,
                score=0.0,
                confidence=1.0,
                risk_level="critical",
            )
        reviewer = self.reviewers.get(str(preferred).lower())
        if reviewer is None:
            return ReviewResult(
                local.reviewer,
                local.model,
                local.prompt_version,
                local.status,
                local.summary,
                local.input_hash,
                local.latency_ms,
                fallback_used=True,
            )
        try:
            return await reviewer(signal)
        except Exception as exc:
            return ReviewResult(
                local.reviewer,
                local.model,
                local.prompt_version,
                "degraded",
                local.summary,
                local.input_hash,
                local.latency_ms,
                fallback_used=True,
                error=type(exc).__name__,
            )


__all__ = ["AIReviewRouter", "ReviewResult", "review_signal"]
