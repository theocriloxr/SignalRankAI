"""Opt-in, fail-closed shortlist for new SignalRank market scans.

This is a scanning boundary, NOT broker execution eligibility or an automatic
live-trading authorization. The legacy all-market universe remains unchanged
until a separately verified release enables FOCUSED_UNIVERSE_ENABLED.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping

from core.asset_registry import canonicalize_asset, resolve_asset_spec

_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "focused_universe.json"
_CLASS_NAMES = frozenset(("crypto", "forex", "index", "equity", "commodity"))
_ALIASES = {"stock": "equity", "fx": "forex"}
_MAX_PER_CLASS = 15


@dataclass(frozen=True, slots=True)
class FocusedUniverseResult:
    assets: tuple[str, ...]
    selected_per_class: Mapping[str, int]
    offered_count: int
    excluded_count: int


def load_focused_config(path: Path | None = None) -> Mapping[str, object]:
    """Validate shortlist limits before any candidate can be admitted."""
    payload = json.loads((path or _CONFIG).read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != 1
        or payload.get("mode") != "staging_opt_in_only"
        or payload.get("max_active_per_class") != _MAX_PER_CLASS
        or payload.get("core_target_per_class") != 10
    ):
        raise ValueError("focused_universe_invalid_contract")
    groups = payload.get("asset_classes")
    if not isinstance(groups, dict) or set(groups) != _CLASS_NAMES:
        raise ValueError("focused_universe_invalid_classes")
    seen: set[str] = set()
    for klass, group in groups.items():
        if not isinstance(group, dict):
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
    return payload


def select_focused_assets(
    available_symbols: Iterable[str],
    *,
    config: Mapping[str, object] | None = None,
) -> FocusedUniverseResult:
    """Select up to 15 *available* qualified candidates per market class.

    Availability supplied by callers is not a substitute for real-time provider,
    broker/account or order-routing certification. Unknown, misclassified and
    analysis-only symbols are rejected, never filled by static fallbacks.
    """
    policy = config if config is not None else load_focused_config()
    if config is not None:
        # Validate overrides with the same strict contract, not just a matching shape.
        if policy.get("schema_version") != 1 or policy.get("max_active_per_class") != _MAX_PER_CLASS:
            raise ValueError("focused_universe_invalid_override")
        if policy.get("mode") != "staging_opt_in_only" or policy.get("core_target_per_class") != 10:
            raise ValueError("focused_universe_invalid_override")
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
