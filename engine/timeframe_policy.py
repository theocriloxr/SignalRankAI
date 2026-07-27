"""Canonical timeframe requirement policy for SignalRankAI.

This module provides a single resolver for timeframe requirements across
all runtime components: market monitor, engine universe precheck, OHLC fetch,
quality gate, asset results, diagnostics, and tests.

Every consumer must use ``resolve_required_timeframes()`` instead of
duplicating hardcoded rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TradingStyle(StrEnum):
    SCALP = "scalp"
    DAY = "day"
    SWING = "swing"
    POSITION = "position"


# Default timeframe requirements per asset class and trading style.
# Keys: (asset_class, trading_style)
# Values: (list of required timeframes, list of optional timeframes)
_DEFAULT_REQUIREMENTS: dict[tuple[str, str], tuple[list[str], list[str]]] = {
    ("crypto", "scalp"): (["1m", "5m", "15m", "1h"], ["4h", "1d"]),
    ("crypto", "day"): (["5m", "15m", "1h"], ["1m", "4h", "1d"]),
    ("crypto", "swing"): (["1h", "4h"], ["5m", "15m", "1d"]),
    ("crypto", "position"): (["4h", "1d"], ["1h"]),
    ("fx", "scalp"): (["1m", "5m", "15m", "1h"], ["4h", "1d"]),
    ("fx", "day"): (["5m", "15m", "1h"], ["1m", "4h", "1d"]),
    ("fx", "swing"): (["1h", "4h"], ["5m", "15m", "1d"]),
    ("fx", "position"): (["4h", "1d"], ["1h"]),
    ("stock", "scalp"): (["5m", "15m", "1h"], ["4h", "1d"]),
    ("stock", "day"): (["15m", "1h"], ["5m", "4h", "1d"]),
    ("stock", "swing"): (["1h", "4h", "1d"], ["15m"]),
    ("stock", "position"): (["1d"], ["4h"]),
    ("commodity", "swing"): (["1h", "4h", "1d"], ["15m"]),
    ("commodity", "position"): (["4h", "1d"], ["1h"]),
    ("index", "swing"): (["1h", "4h", "1d"], ["15m"]),
    ("index", "position"): (["4h", "1d"], ["1h"]),
}


# Known timeframe strings for validation
_KNOWN_TIMEFRAMES = frozenset({
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"
})


# Policy version: bump when the resolution logic changes
_POLICY_VERSION = "phase4-pass8-v1"


@dataclass(frozen=True, slots=True)
class TimeframeRequirement:
    """Structured result from the canonical resolver."""
    required: tuple[str, ...]
    optional: tuple[str, ...]
    reason: str
    policy_version: str = _POLICY_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "required": list(self.required),
            "optional": list(self.optional),
            "reason": self.reason,
            "policy_version": self.policy_version,
        }


def _classify_asset_for_timeframes(asset_class: str | None) -> str:
    """Normalize asset class to one of the keys in _DEFAULT_REQUIREMENTS."""
    ac = str(asset_class or "crypto").strip().lower()
    aliases = {
        "forex": "fx",
        "equity": "stock",
        "equities": "stock",
        "indices": "index",
        "index": "index",
        "commodities": "commodity",
        "metal": "commodity",
        "metals": "commodity",
        "crypto": "crypto",
        "cryptocurrency": "crypto",
    }
    return aliases.get(ac, "stock")


def _resolve_trading_style(
    strategy_profile: str | None,
    requested_timeframe: str | None,
) -> TradingStyle:
    """Infer trading style from strategy profile or requested timeframe."""
    profile = str(strategy_profile or "").strip().lower()
    if profile in {"scalp", "day", "swing", "position"}:
        return TradingStyle(profile)

    # Infer from requested timeframe if no profile set
    tf = str(requested_timeframe or "").strip().lower()
    if tf in ("1m", "3m", "5m"):
        return TradingStyle.SCALP
    if tf in ("15m", "30m"):
        return TradingStyle.DAY
    if tf in ("1h", "2h", "4h"):
        return TradingStyle.SWING
    if tf in ("6h", "8h", "12h", "1d"):
        return TradingStyle.POSITION

    # Default to swing for unknown contexts
    return TradingStyle.SWING


def resolve_required_timeframes(
    asset_class: str | None,
    strategy_profile: str | None = None,
    requested_timeframe: str | None = None,
    trading_style: str | None = None,
    runtime_context: dict[str, Any] | None = None,
) -> TimeframeRequirement:
    """Resolve the canonical set of required and optional timeframes.

    Args:
        asset_class: Asset class (crypto, fx, stock, commodity, index).
        strategy_profile: Strategy profile name (scalp, day, swing, position).
        requested_timeframe: The primary timeframe being evaluated.
        trading_style: Explicit trading style override.
        runtime_context: Optional runtime context for future customization.

    Returns:
        A TimeframeRequirement with required and optional timeframes.
    """
    normalized_class = _classify_asset_for_timeframes(asset_class)

    if trading_style:
        try:
            style = TradingStyle(trading_style.strip().lower())
        except ValueError:
            style = _resolve_trading_style(strategy_profile, requested_timeframe)
    else:
        style = _resolve_trading_style(strategy_profile, requested_timeframe)

    key = (normalized_class, style.value)
    defaults = _DEFAULT_REQUIREMENTS.get(key)

    if defaults is None:
        # Fallback: try with swing style for unknown combinations
        fallback_key = (normalized_class, TradingStyle.SWING.value)
        defaults = _DEFAULT_REQUIREMENTS.get(fallback_key, (["1h"], ["4h", "1d"]))

    required_tfs, optional_tfs = defaults

    # If requested_timeframe is specified and not in required, add it
    if requested_timeframe:
        tf = requested_timeframe.strip().lower()
        if tf in _KNOWN_TIMEFRAMES and tf not in required_tfs and tf not in optional_tfs:
            optional_tfs = [tf] + optional_tfs

    reason = (
        f"asset_class={normalized_class} "
        f"trading_style={style.value} "
        f"profile={strategy_profile or 'auto'} "
        f"requested_tf={requested_timeframe or 'auto'}"
    )

    return TimeframeRequirement(
        required=tuple(required_tfs),
        optional=tuple(optional_tfs),
        reason=reason,
    )


def validate_timeframe_requirement(
    available_timeframes: dict[str, bool],
    asset_class: str | None,
    strategy_profile: str | None = None,
    requested_timeframe: str | None = None,
    trading_style: str | None = None,
) -> tuple[bool, str, TimeframeRequirement | None]:
    """Validate that available timeframes meet the requirement.

    Args:
        available_timeframes: Dict mapping timeframe -> whether it's available.
        asset_class, strategy_profile, requested_timeframe, trading_style:
            Passed through to resolve_required_timeframes().

    Returns:
        Tuple of (is_valid, reason, requirement).
    """
    req = resolve_required_timeframes(
        asset_class=asset_class,
        strategy_profile=strategy_profile,
        requested_timeframe=requested_timeframe,
        trading_style=trading_style,
    )

    missing = [tf for tf in req.required if not available_timeframes.get(tf, False)]
    if missing:
        return (
            False,
            f"missing_required_timeframe:{','.join(missing)}",
            req,
        )

    return (True, "all_required_timeframes_available", req)


__all__ = [
    "TimeframeRequirement",
    "TradingStyle",
    "resolve_required_timeframes",
    "validate_timeframe_requirement",
]
