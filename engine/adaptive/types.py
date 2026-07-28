from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class EvidenceQuality(str, Enum):
    GENUINE = "genuine"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class ProfileState(str, Enum):
    DRAFT = "DRAFT"
    RESEARCH = "RESEARCH"
    BACKTEST_QUALIFIED = "BACKTEST_QUALIFIED"
    WALK_FORWARD_QUALIFIED = "WALK_FORWARD_QUALIFIED"
    SHADOW = "SHADOW"
    FORWARD_TEST = "FORWARD_TEST"
    CANARY = "CANARY"
    LIMITED_LIVE = "LIMITED_LIVE"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"
    ROLLED_BACK = "ROLLED_BACK"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    usable: bool
    score: float
    candle_count: int
    stale: bool = False
    duplicate_count: int = 0
    gap_count: int = 0
    impossible_count: int = 0
    missing_count: int = 0
    provider: str = "unknown"
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PriceZone:
    kind: str
    lower: float
    upper: float
    lifecycle: str = "active"
    confidence: float = 0.0
    created_index: int | None = None
    invalidation: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MarketContext:
    asset: str
    asset_class: str
    timeframe: str
    candles: tuple[Mapping[str, Any], ...]
    indicators: Mapping[str, Any]
    regime: str
    session: str
    provider: str
    data_quality: DataQualityReport
    higher_timeframe_bias: str | None = None
    news_context: Mapping[str, Any] = field(default_factory=dict)
    macro_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyEvidence:
    strategy_id: str
    strategy_version: str
    family: str
    asset: str
    asset_class: str
    timeframe: str
    direction: Direction
    setup_type: str
    confidence: float
    raw_score: float
    zones: tuple[PriceZone, ...] = ()
    entry_proposal: float | None = None
    stop_proposal: float | None = None
    target_proposals: tuple[float, ...] = ()
    invalidation: str | None = None
    regime_compatibility: float = 0.0
    data_quality: DataQualityReport | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    conflicts: tuple[str, ...] = ()
    duplicate_fingerprint: str = ""
    evidence_quality: EvidenceQuality = EvidenceQuality.GENUINE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["direction"] = self.direction.value
        payload["evidence_quality"] = self.evidence_quality.value
        return payload


@dataclass(frozen=True, slots=True)
class AssetStrategyProfile:
    profile_id: str
    asset: str
    asset_class: str
    version: int
    state: ProfileState
    source_scope: str = "global"
    preferred_families: tuple[str, ...] = ()
    penalised_families: tuple[str, ...] = ()
    disabled_families: tuple[str, ...] = ()
    preferred_timeframes: tuple[str, ...] = ()
    preferred_sessions: tuple[str, ...] = ()
    avoided_sessions: tuple[str, ...] = ()
    regime_weights: Mapping[str, float] = field(default_factory=dict)
    family_weights: Mapping[str, float] = field(default_factory=dict)
    minimum_confidence: float = 0.70
    minimum_reward_risk: float = 1.5
    maximum_score_multiplier: float = 1.15
    minimum_score_multiplier: float = 0.85
    data_sufficiency_score: float = 0.0
    sample_size: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def approved_for_runtime(self) -> bool:
        return self.state in {ProfileState.APPROVED, ProfileState.LIMITED_LIVE, ProfileState.CANARY}

    def family_multiplier(self, family: str, regime: str, session: str, timeframe: str) -> float:
        if not self.approved_for_runtime:
            return 1.0
        family_key = str(family or "unknown").strip().lower()
        if family_key in {x.lower() for x in self.disabled_families}:
            return 0.0
        value = float(self.family_weights.get(family_key, 1.0) or 1.0)
        value *= float(self.regime_weights.get(str(regime or "unknown").lower(), 1.0) or 1.0)
        if self.preferred_families and family_key in {x.lower() for x in self.preferred_families}:
            value *= 1.05
        if family_key in {x.lower() for x in self.penalised_families}:
            value *= 0.90
        if self.preferred_timeframes and timeframe not in self.preferred_timeframes:
            value *= 0.95
        if session in self.avoided_sessions:
            value *= 0.85
        elif self.preferred_sessions and session in self.preferred_sessions:
            value *= 1.03
        return max(self.minimum_score_multiplier, min(self.maximum_score_multiplier, value))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


@dataclass(frozen=True, slots=True)
class AdaptiveAssessment:
    asset: str
    asset_class: str
    regime: str
    session: str
    profile: AssetStrategyProfile
    evidence: tuple[StrategyEvidence, ...]
    conflicts: tuple[str, ...]
    data_quality_score: float
    sequence_references: tuple[Mapping[str, Any], ...]
    runtime_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "asset_class": self.asset_class,
            "regime": self.regime,
            "session": self.session,
            "profile": self.profile.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "conflicts": list(self.conflicts),
            "data_quality_score": self.data_quality_score,
            "sequence_references": [dict(x) for x in self.sequence_references],
            "runtime_mode": self.runtime_mode,
        }


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if out != out or out in {float("inf"), float("-inf")}:
            return float(default)
        return out
    except (TypeError, ValueError):
        return float(default)


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))
