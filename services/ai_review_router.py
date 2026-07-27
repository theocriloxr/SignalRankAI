"""Deterministic-first AI review router with safe provider fallbacks."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping


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


def _local_review(signal: Mapping[str, Any]) -> ReviewResult:
    started = time.perf_counter()
    asset = str(signal.get("asset") or "unknown")
    direction = str(signal.get("direction") or "unknown").upper()
    entry = signal.get("entry")
    stop = signal.get("stop_loss") or signal.get("stop")
    summary = f"{asset} {direction}: deterministic review requires fresh quote, ordered stop/targets, and explicit risk limits."
    digest = hashlib.sha256(repr(sorted(signal.items())).encode()).hexdigest()[:24]
    return ReviewResult("local", "deterministic-v1", "local-review-v1", "ok", summary, digest, (time.perf_counter() - started) * 1000)


class AIReviewRouter:
    def __init__(self, reviewers: Mapping[str, Callable[[Mapping[str, Any]], Awaitable[ReviewResult]]] | None = None) -> None:
        self.reviewers = dict(reviewers or {})

    async def review(self, signal: Mapping[str, Any], *, preferred: str = "gemini") -> ReviewResult:
        # Deterministic structural veto always runs first.
        local = _local_review(signal)
        try:
            entry = float(signal.get("entry") or 0)
            stop = float(signal.get("stop_loss") or signal.get("stop") or 0)
        except (TypeError, ValueError):
            entry, stop = 0.0, 0.0
        direction = str(signal.get("direction") or "").lower()
        if entry <= 0 or stop <= 0 or (direction in {"long", "buy"} and stop >= entry) or (direction in {"short", "sell"} and stop <= entry):
            return ReviewResult(local.reviewer, local.model, local.prompt_version, "blocked", "Deterministic risk structure is invalid; AI cannot override it.", local.input_hash, local.latency_ms)
        reviewer = self.reviewers.get(str(preferred).lower())
        if reviewer is None:
            return ReviewResult(local.reviewer, local.model, local.prompt_version, local.status, local.summary, local.input_hash, local.latency_ms, fallback_used=True)
        try:
            result = await reviewer(signal)
            return result
        except Exception as exc:
            return ReviewResult(local.reviewer, local.model, local.prompt_version, "degraded", local.summary, local.input_hash, local.latency_ms, fallback_used=True, error=type(exc).__name__)


__all__ = ["AIReviewRouter", "ReviewResult"]
