"""Asset-class certification framework (Phase 5).

A tradable asset class is not "ready" until it proves the full delivery chain:
universe -> symbol mapping -> candles -> authoritative live quote -> freshness
-> generation -> geometry -> persistence -> delivery -> proof -> paper open ->
outcome monitoring -> close -> performance projection -> failover -> market
hours -> diagnostics.

Readiness states:

    unsupported / configured / market_data_partial / analysis_ready /
    delivery_ready / paper_ready / testnet_ready / live_guarded / degraded / blocked

This module is pure and dependency-free: callers (owner diagnostics, engine
startup, health reports) supply evidence collected from the actual runtime.
A disabled real-money side effect reports ``safe-mode-ready`` semantics via
``live_guarded`` when the complete safe workflow exists, never ``unsupported``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ReadinessState(str, Enum):
    UNSUPPORTED = "unsupported"
    CONFIGURED = "configured"
    MARKET_DATA_PARTIAL = "market_data_partial"
    ANALYSIS_READY = "analysis_ready"
    DELIVERY_READY = "delivery_ready"
    PAPER_READY = "paper_ready"
    TESTNET_READY = "testnet_ready"
    LIVE_GUARDED = "live_guarded"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


#: The 17-step certification chain, in dependency order.
CERTIFICATION_STEPS: tuple[str, ...] = (
    "symbol_discovery",      # 1  universe populated / configured
    "canonical_mapping",     # 2  canonical symbol mapping
    "historical_candles",    # 3  required historical candles
    "live_bid_ask",          # 4  authoritative live bid/ask or tradable price
    "fresh_timestamp",       # 5  fresh provider timestamp
    "signal_generation",     # 6  signal generation
    "valid_geometry",        # 7  valid geometry
    "signal_persistence",    # 8  signal persistence
    "telegram_delivery",     # 9  telegram delivery
    "delivery_proof",        # 10 delivery proof
    "paper_open",            # 11 paper-trade opening
    "outcome_monitoring",    # 12 outcome monitoring
    "position_close",        # 13 position closing
    "performance_projection",  # 14 performance projection
    "provider_failover",     # 15 provider failover
    "market_hours",          # 16 market-hours handling
    "production_diagnostics",  # 17 production diagnostics
)

#: Steps that depend on a later gate; used to explain degraded states.
_ANALYSIS_STEPS = {"symbol_discovery", "canonical_mapping", "historical_candles", "live_bid_ask", "fresh_timestamp"}
_DELIVERY_STEPS = {"signal_generation", "valid_geometry", "signal_persistence", "telegram_delivery", "delivery_proof"}
_PAPER_STEPS = {"paper_open", "outcome_monitoring", "position_close", "performance_projection"}
_RELIABILITY_STEPS = {"provider_failover", "market_hours", "production_diagnostics"}

SUPPORTED_ASSET_CLASSES: tuple[str, ...] = (
    "crypto", "crypto_perpetual", "fx", "index", "commodity", "stock",
    "macro", "volatility", "bond", "rates",
)

#: Environment-role macro series that are contextual unless a tradable venue exists.
CONTEXTUAL_ONLY: frozenset[str] = frozenset({"macro", "volatility", "rates"})


def _evidence_ok(evidence: Mapping[str, Any], step: str) -> bool:
    value = evidence.get(step)
    if isinstance(value, Mapping):
        return bool(value.get("ok"))
    return bool(value)


def _evidence_detail(evidence: Mapping[str, Any], step: str) -> str:
    value = evidence.get(step)
    if isinstance(value, Mapping):
        detail = value.get("detail")
        return str(detail) if detail else ""
    return ""


@dataclass(frozen=True, slots=True)
class CertificationResult:
    asset_class: str
    readiness: ReadinessState
    ready_steps: tuple[str, ...]
    missing_steps: tuple[str, ...]
    blocked_reason: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def coverage_pct(self) -> float:
        total = len(CERTIFICATION_STEPS)
        return round(len(self.ready_steps) / total * 100.0, 1) if total else 0.0

    def summary_line(self) -> str:
        return (
            f"{self.asset_class}: {self.readiness.value} "
            f"({len(self.ready_steps)}/{len(CERTIFICATION_STEPS)} steps, "
            f"{self.coverage_pct:.0f}%)"
        )


def evaluate_certification(
    asset_class: str,
    evidence: Mapping[str, Any],
    *,
    testnet_ready: bool = False,
    live_guarded: bool = False,
    blocked_reason: str = "",
) -> CertificationResult:
    """Evaluate the 17-step chain for one asset class from runtime evidence."""
    cls = str(asset_class or "").strip().lower().replace(" ", "_")
    if not cls:
        return CertificationResult(cls, ReadinessState.UNSUPPORTED, (), CERTIFICATION_STEPS)
    if cls not in SUPPORTED_ASSET_CLASSES:
        return CertificationResult(cls, ReadinessState.UNSUPPORTED, (), CERTIFICATION_STEPS)
    if blocked_reason:
        return CertificationResult(cls, ReadinessState.BLOCKED, (), CERTIFICATION_STEPS, blocked_reason=blocked_reason)
    if cls in CONTEXTUAL_ONLY:
        # Contextual series are only delivery-ready when mapped to a tradable venue.
        if not _evidence_ok(evidence, "canonical_mapping"):
            return CertificationResult(cls, ReadinessState.CONFIGURED, (), CERTIFICATION_STEPS, notes=("contextual_series_no_tradable_venue",))

    ready = tuple(step for step in CERTIFICATION_STEPS if _evidence_ok(evidence, step))
    missing = tuple(step for step in CERTIFICATION_STEPS if step not in ready)
    ready_set = set(ready)
    notes: list[str] = []

    # Degraded: known asset class but live-quote reliability broken (XAGUSD-style).
    if (
        _evidence_ok(evidence, "historical_candles")
        and not _evidence_ok(evidence, "live_bid_ask")
        and not blocked_reason
    ):
        # Distinguish "not yet enabled" from "enabled but failing".
        provider_status = str(evidence.get("provider_status") or "").strip().lower()
        if provider_status and provider_status not in {"", "none", "disabled", "not_configured"}:
            return CertificationResult(cls, ReadinessState.DEGRADED, ready, missing, notes=("live_quote_route_unreliable",))

    if not (_ANALYSIS_STEPS & ready_set):
        return CertificationResult(cls, ReadinessState.CONFIGURED, ready, missing, notes=tuple(notes))
    if not (_evidence_ok(evidence, "live_bid_ask") and _evidence_ok(evidence, "fresh_timestamp")):
        state = ReadinessState.MARKET_DATA_PARTIAL if _evidence_ok(evidence, "historical_candles") else ReadinessState.CONFIGURED
        return CertificationResult(cls, state, ready, missing, notes=tuple(notes))
    if not (_DELIVERY_STEPS & ready_set) or not (_DELIVERY_STEPS <= ready_set):
        return CertificationResult(cls, ReadinessState.ANALYSIS_READY, ready, missing, notes=tuple(notes))
    if not (_PAPER_STEPS <= ready_set):
        return CertificationResult(cls, ReadinessState.DELIVERY_READY, ready, missing, notes=tuple(notes))
    if not (_RELIABILITY_STEPS <= ready_set):
        return CertificationResult(cls, ReadinessState.PAPER_READY, ready, missing, notes=tuple(notes))
    if testnet_ready and not live_guarded:
        return CertificationResult(cls, ReadinessState.TESTNET_READY, ready, missing, notes=("testnet_certified",))
    if live_guarded:
        return CertificationResult(cls, ReadinessState.LIVE_GUARDED, ready, missing, notes=("guarded_activation_only",))
    return CertificationResult(cls, ReadinessState.PAPER_READY, ready, missing, notes=("paper_ready_live_not_enabled",))


def readiness_label(state: ReadinessState) -> str:
    """Human-safe label used in owner diagnostics."""
    return {
        ReadinessState.UNSUPPORTED: "unsupported",
        ReadinessState.CONFIGURED: "configured",
        ReadinessState.MARKET_DATA_PARTIAL: "market-data partial",
        ReadinessState.ANALYSIS_READY: "analysis ready",
        ReadinessState.DELIVERY_READY: "delivery ready",
        ReadinessState.PAPER_READY: "paper ready",
        ReadinessState.TESTNET_READY: "testnet ready",
        ReadinessState.LIVE_GUARDED: "live guarded (safe-mode-ready)",
        ReadinessState.DEGRADED: "degraded",
        ReadinessState.BLOCKED: "blocked",
    }[state]


__all__ = [
    "CERTIFICATION_STEPS",
    "CONTEXTUAL_ONLY",
    "SUPPORTED_ASSET_CLASSES",
    "CertificationResult",
    "ReadinessState",
    "evaluate_certification",
    "readiness_label",
]
