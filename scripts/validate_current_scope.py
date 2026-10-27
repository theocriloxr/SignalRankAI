"""Validate the current, unactivated user-scoped trading-universe contract.

This checks Stage 1 source preservation only. It does not enable scanning,
classify broker symbols as tradable, or authorize any production trades.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCOPE_PATH = ROOT / "docs/release/current_scope_20261016.json"
CLASSES = frozenset({"crypto", "forex", "index", "equity", "commodity"})
REQUIRED_TRUE = (
    "qualification_required",
    "provider_mapping_required",
    "broker_account_certification_required",
    "execution_requires_independent_authorization",
    "new_entry_blocked_for_excluded_instruments",
    "manage_existing_positions_when_excluded",
    "retain_historical_data",
    "no_production_permission_change_authorized",
    "no_live_order_tests_authorized",
)
REQUIRED_FALSE = ("core_is_guaranteed_active", "allow_unqualified_fallback")


def validate_scope(doc: dict[str, Any]) -> dict[str, int]:
    """Reject a silently broadened, stale or implicitly activated universe."""
    if doc.get("schema_version") != 1 or doc.get("requirement_id") != "SR-FOCUS-20261015":
        raise ValueError("unexpected_current_scope_identity")
    if doc.get("status") != "NOT_IMPLEMENTED":
        raise ValueError("scope_claims_implementation_without_runtime_acceptance")
    classes = doc.get("asset_classes")
    if not isinstance(classes, dict) or set(classes) != CLASSES:
        raise ValueError("invalid_class_set")
    p = doc.get("policy")
    if not isinstance(p, dict) or p.get("max_active_per_class") != 15 or p.get("preferred_core_candidates_per_class") != 10:
        raise ValueError("invalid_focus_limits")
    for name in REQUIRED_TRUE:
        if p.get(name) is not True:
            raise ValueError("unsafe_scope_policy:" + name)
    for name in REQUIRED_FALSE:
        if p.get(name) is not False:
            raise ValueError("unsafe_scope_policy:" + name)
    result: dict[str, int] = {}
    seen_across_classes: set[str] = set()
    for asset_class in sorted(CLASSES):
        group = classes[asset_class]
        if not isinstance(group, dict):
            raise ValueError("invalid_group:" + asset_class)
        core, optional = group.get("core"), group.get("optional")
        if not isinstance(core, list) or not isinstance(optional, list) or len(core) != 10 or len(optional) > 5:
            raise ValueError("invalid_candidate_counts:" + asset_class)
        symbols = core + optional
        if any(not isinstance(s, str) or not s or s != s.strip().upper() for s in symbols):
            raise ValueError("invalid_symbol_format:" + asset_class)
        if len(set(symbols)) != len(symbols) or seen_across_classes.intersection(symbols):
            raise ValueError("duplicate_candidate:" + asset_class)
        seen_across_classes.update(symbols)
        result[asset_class] = len(symbols)
    return result


def main() -> int:
    doc = json.loads(SCOPE_PATH.read_text(encoding="utf-8"))
    counts = validate_scope(doc)
    print(json.dumps({"scope_only": True, "production_unchanged": True, "candidate_counts": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
