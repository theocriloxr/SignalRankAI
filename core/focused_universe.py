"""Opt-in, fail-closed shortlist for new SignalRank market scans.

This is a scanning boundary, NOT broker execution eligibility or an automatic
live-trading authorization. The legacy all-market universe remains unchanged
until a separately verified release enables FOCUSED_UNIVERSE_ENABLED.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Iterable, Mapping

from core.asset_registry import canonicalize_asset, resolve_asset_spec

_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "focused_universe.json"
_CLASS_NAMES = frozenset(("crypto", "forex", "index", "equity", "commodity"))
_ALIASES = {"stock": "equity", "fx": "forex"}
_MAX_PER_CLASS = 15
_NONPRODUCTION = frozenset(("staging", "stage", "development", "dev", "test"))


@dataclass(frozen=True, slots=True)
class FocusedUniverseResult:
    assets: tuple[str, ...]
    selected_per_class: Mapping[str, int]
    offered_count: int
    excluded_count: int


def load_focused_config(path: Path | None = None) -> Mapping[str, object]:
    """Validate shortlist limits before any candidate can be admitted."""
    payload = json.loads((path or _CONFIG).read_text(encoding="utf-8"))
    validate_focused_config(payload)
    return payload


def validate_focused_config(payload: Mapping[str, object]) -> None:
    """Apply the same contract to disk configuration and in-memory overrides."""
    if not isinstance(payload, Mapping):
        raise ValueError("focused_universe_invalid_contract")
    if (
        type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != 1
        or payload.get("mode") != "staging_opt_in_only"
        or type(payload.get("max_active_per_class")) is not int
        or payload.get("max_active_per_class") != _MAX_PER_CLASS
        or type(payload.get("core_target_per_class")) is not int
        or payload.get("core_target_per_class") != 10
    ):
        raise ValueError("focused_universe_invalid_contract")
    groups = payload.get("asset_classes")
    if not isinstance(groups, Mapping) or set(groups) != _CLASS_NAMES:
        raise ValueError("focused_universe_invalid_classes")
    seen: set[str] = set()
    for klass, group in groups.items():
        if not isinstance(group, Mapping):
            raise ValueError("focused_universe_invalid_group:" + klass)
        core, optional = group.get("core"), group.get("optional")
        if not isinstance(core, list) or not isinstance(optional, list) or len(core) != 10 or len(optional) > 5:
            raise ValueError("focused_universe_invalid_counts:" + klass)
        for symbol in core + optional:
            if not isinstance(symbol, str) or not symbol or symbol != symbol.strip().upper():
                raise ValueError("focused_universe_invalid_symbol:" + klass)
            canonical = canonicalize_asset(symbol)
            if canonical in seen:
                raise ValueError("focused_universe_duplicate_symbol:" + canonical)
            seen.add(canonical)


def focused_universe_enabled(environment: Mapping[str, str]) -> bool:
    """Fail closed on ambiguous flags or any conflicting environment label.

    An APP_ENV=test override must not hide Railway production, nor may a
    Railway staging label hide APP_ENV=production. This does not change flags.
    """
    flag = environment.get("FOCUSED_UNIVERSE_ENABLED", "0").strip().lower()
    if flag in {"", "0", "false", "no", "off"}:
        return False
    if flag not in {"1", "true", "yes", "on"}:
        raise ValueError("focused_universe_invalid_enable_flag")
    labels = [environment.get(key, "").strip().lower() for key in (
        "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT", "APP_ENV", "ENVIRONMENT"
    )]
    declared = [label for label in labels if label]
    if not declared or any(label not in _NONPRODUCTION for label in declared):
        raise RuntimeError("focused_universe_requires_staging_certification")
    return True


@lru_cache(maxsize=1)
def focused_shortlist() -> frozenset[str]:
    """Canonical shortlist members that classify into their declared class.

    Derived from the validated configuration only; no provider, broker or
    account availability is implied by membership.
    """
    policy = load_focused_config()
    groups = policy["asset_classes"]
    symbols: list[str] = []
    for group in groups.values():  # type: ignore[union-attr]
        symbols.extend(group["core"] + group["optional"])
    return frozenset(select_focused_assets(symbols, config=policy).assets)


def focused_admission(
    asset: object, environment: Mapping[str, str] | None = None,
) -> tuple[bool, str]:
    """Single new-entry admission check for every path that creates exposure.

    Applies only while the opt-in focused universe is enabled in an isolated,
    non-production environment. A flag set in production fails closed: new
    entries are refused rather than silently falling back to the full universe.
    Existing signals, positions and history are never affected by this check.
    """
    env = os.environ if environment is None else environment
    try:
        enabled = focused_universe_enabled(env)
    except (RuntimeError, ValueError) as exc:
        return False, str(exc)
    if not enabled:
        return True, "focused_universe_disabled"
    if not isinstance(asset, str) or not asset.strip():
        return False, "focused_universe_missing_asset"
    try:
        canonical = canonicalize_asset(asset)
        shortlist = focused_shortlist()
    except (OSError, ValueError, KeyError) as exc:
        return False, "focused_universe_config_unavailable:" + type(exc).__name__
    if canonical in shortlist:
        return True, "focused_shortlist_member"
    return False, "focused_universe_excluded"


def select_focused_scan_assets(
    database_symbols: Iterable[str], *, universe_source: str,
    environment: Mapping[str, str],
) -> FocusedUniverseResult:
    """Accept only the pre-discovery DB snapshot in explicitly isolated runs.

    Pinned assets and class-completion fallbacks are deliberately not inputs.
    Database analysis-readiness is still not external provider certification.
    """
    if not focused_universe_enabled(environment):
        raise RuntimeError("focused_universe_not_enabled")
    available = database_symbols if universe_source == "database_registry" else ()
    return select_focused_assets(available)


def select_focused_assets(
    available_symbols: Iterable[str],
    *,
    config: Mapping[str, object] | None = None,
) -> FocusedUniverseResult:
    """Select up to 15 available shortlist candidates per market class.

    Availability supplied by callers is not a substitute for real-time provider,
    broker/account or order-routing certification. Unknown, misclassified and
    analysis-only symbols are rejected, never filled by static fallbacks.
    """
    policy = config if config is not None else load_focused_config()
    validate_focused_config(policy)
    groups = policy["asset_classes"]
    if not isinstance(groups, Mapping) or set(groups) != _CLASS_NAMES:
        raise ValueError("focused_universe_invalid_classes")
    available = {
        canonicalize_asset(raw) for raw in available_symbols if isinstance(raw, str) and raw.strip()
    }
    selected: list[str] = []
    counts: dict[str, int] = {}
    for klass in ("crypto", "forex", "index", "equity", "commodity"):
        group = groups[klass]
        if not isinstance(group, Mapping):
            raise ValueError("focused_universe_invalid_group")
        core, optional = group["core"], group["optional"]
        if not isinstance(core, list) or not isinstance(optional, list) or len(core) != 10 or len(optional) > 5:
            raise ValueError("focused_universe_invalid_counts")
        count = 0
        for candidate in core + optional:
            canonical = canonicalize_asset(candidate)
            if canonical not in available or canonical in selected:
                continue
            spec = resolve_asset_spec(canonical, allow_dynamic_equity=True)
            actual_class = _ALIASES.get(spec.asset_class, spec.asset_class)
            if actual_class != klass or not spec.actionable or spec.analysis_only:
                continue
            if count >= _MAX_PER_CLASS:
                break
            selected.append(canonical)
            count += 1
        counts[klass] = count
    return FocusedUniverseResult(
        assets=tuple(selected),
        selected_per_class=counts,
        offered_count=len(available),
        excluded_count=len(available.difference(selected)),
    )
