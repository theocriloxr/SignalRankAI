from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict


@dataclass(frozen=True)
class DCAProfile:
    name: str
    base_order_usd: float
    max_legs: int
    initial_spacing_pct: float
    volume_scale: float
    step_scale: float


@dataclass(frozen=True)
class DCARegimeAdaptive:
    low_vol_initial_spacing_pct: float
    low_vol_max_legs: int
    high_vol_initial_spacing_pct: float
    high_vol_step_scale: float


@dataclass(frozen=True)
class DCALevel:
    leg_index: int
    trigger_drop_pct: float
    order_size_usd: float


def conservative_swing_profile() -> DCAProfile:
    return DCAProfile(
        name="conservative_swing",
        base_order_usd=100.0,
        max_legs=4,
        initial_spacing_pct=2.0,
        volume_scale=1.5,
        step_scale=1.2,
    )


def aggressive_mean_reversion_profile() -> DCAProfile:
    return DCAProfile(
        name="aggressive_mean_reversion",
        base_order_usd=50.0,
        max_legs=6,
        initial_spacing_pct=1.5,
        volume_scale=2.0,
        step_scale=1.5,
    )


def ml_adaptive_defaults() -> DCARegimeAdaptive:
    return DCARegimeAdaptive(
        low_vol_initial_spacing_pct=1.0,
        low_vol_max_legs=3,
        high_vol_initial_spacing_pct=3.5,
        high_vol_step_scale=1.4,
    )


def adaptive_profile_for_regime(regime: str) -> DCAProfile:
    regime_norm = str(regime or "").strip().lower()
    adapt = ml_adaptive_defaults()
    if regime_norm in {"high_vol", "volatile", "news_spike"}:
        return DCAProfile(
            name="ml_adaptive_high_vol",
            base_order_usd=100.0,
            max_legs=4,
            initial_spacing_pct=adapt.high_vol_initial_spacing_pct,
            volume_scale=1.5,
            step_scale=adapt.high_vol_step_scale,
        )
    return DCAProfile(
        name="ml_adaptive_low_vol",
        base_order_usd=100.0,
        max_legs=adapt.low_vol_max_legs,
        initial_spacing_pct=adapt.low_vol_initial_spacing_pct,
        volume_scale=1.5,
        step_scale=1.2,
    )


def resolve_profile(profile_name: str, regime: str | None = None) -> DCAProfile:
    name = str(profile_name or "").strip().lower()
    if name == "aggressive_mean_reversion":
        return aggressive_mean_reversion_profile()
    if name == "ml_adaptive":
        return adaptive_profile_for_regime(regime or "low_vol")
    return conservative_swing_profile()


def build_dca_levels(profile: DCAProfile) -> List[DCALevel]:
    levels: List[DCALevel] = []
    cumulative_drop = 0.0
    next_spacing = float(profile.initial_spacing_pct)
    order_size = float(profile.base_order_usd)

    for idx in range(1, int(profile.max_legs) + 1):
        cumulative_drop += next_spacing
        levels.append(
            DCALevel(
                leg_index=idx,
                trigger_drop_pct=round(cumulative_drop, 4),
                order_size_usd=round(order_size, 4),
            )
        )
        next_spacing *= float(profile.step_scale)
        order_size *= float(profile.volume_scale)

    return levels


def profile_summary(profile: DCAProfile) -> Dict[str, float | int | str]:
    levels = build_dca_levels(profile)
    covered_drop = levels[-1].trigger_drop_pct if levels else 0.0
    total_capital = sum(level.order_size_usd for level in levels)
    return {
        "name": profile.name,
        "max_legs": profile.max_legs,
        "covered_drop_pct": round(float(covered_drop), 4),
        "total_dca_capital_usd": round(float(total_capital), 4),
    }
