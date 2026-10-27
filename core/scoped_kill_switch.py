"""Strategy, instrument and asset-class execution kill switches (CX-RISK-04).

The global switch (``state.get_killswitch``) stops all execution. These scoped
switches stop one strategy, one instrument or one asset class while leaving the
rest untouched. They only ever add blocks: an unreadable store blocks every
execution, exactly like an unreadable global switch. Every change is recorded
in a bounded audit trail kept with the switch document.
"""
from __future__ import annotations

import re
import time
from typing import Any, Mapping

SCOPES = ("strategy", "instrument", "asset_class")
AUDIT_LIMIT = 200
_KEY_SHAPE = re.compile(r"^[A-Z0-9][A-Z0-9_.:/-]{0,63}$")
UNAVAILABLE = "scoped_kill_switch_unavailable"


def _canonical_class(value: Any) -> str:
    from core.asset_classes import canonical_asset_class

    return canonical_asset_class(value).value.upper()


def _canonical_instrument(value: Any) -> str:
    from core.asset_registry import canonicalize_asset

    return str(canonicalize_asset(str(value or "")) or "").strip().upper()


def normalize_key(scope: str, key: Any) -> str:
    if scope not in SCOPES:
        raise ValueError("scoped_kill_switch_invalid_scope")
    raw = str(key or "").strip()
    try:
        if scope == "asset_class":
            raw = _canonical_class(raw)
        elif scope == "instrument":
            raw = _canonical_instrument(raw)
    except Exception:
        raise ValueError("scoped_kill_switch_invalid_key") from None
    normalized = raw.upper()
    if not _KEY_SHAPE.match(normalized):
        raise ValueError("scoped_kill_switch_invalid_key")
    return normalized


def apply_change(
    document: Mapping[str, Any] | None,
    *,
    scope: str,
    key: Any,
    active: bool,
    actor: str,
    reason: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Return a new document with one switch engaged or released and audited."""
    normalized = normalize_key(scope, key)
    actor_label = str(actor or "").strip()
    if not actor_label:
        raise ValueError("scoped_kill_switch_actor_required")
    stamp = float(time.time() if now is None else now)
    source = dict(document or {})
    switches = {name: dict((source.get("switches") or {}).get(name) or {}) for name in SCOPES}
    previous = normalized in switches[scope]
    if active:
        switches[scope][normalized] = {"reason": str(reason or "")[:200], "actor": actor_label, "since": stamp}
    else:
        switches[scope].pop(normalized, None)
    audit = list(source.get("audit") or [])
    audit.append({
        "at": stamp,
        "actor": actor_label,
        "action": "engage" if active else "release",
        "scope": scope,
        "key": normalized,
        "reason": str(reason or "")[:200],
        "was_active": previous,
    })
    return {"switches": switches, "audit": audit[-AUDIT_LIMIT:], "updated_at": stamp}


def _strategy_of(signal: Mapping[str, Any]) -> str:
    for field in ("strategy", "strategy_id", "strategy_name"):
        value = signal.get(field)
        if value:
            return str(value)
    return ""


def _asset_class_of(signal: Mapping[str, Any], symbol: str) -> str:
    for field in ("asset_class", "class", "market"):
        value = signal.get(field)
        if value:
            try:
                return _canonical_class(value)
            except ValueError:
                continue
    if symbol:
        try:
            from core.asset_registry import resolve_asset_spec

            return _canonical_class(resolve_asset_spec(symbol, allow_dynamic_equity=True).asset_class)
        except Exception:
            return ""
    return ""


def blocking_switches(document: Mapping[str, Any] | None, signal: Mapping[str, Any]) -> list[str]:
    """Names of engaged switches that match this signal, e.g. ``instrument:BTCUSDT``."""
    switches = (document or {}).get("switches") or {}
    symbol = str(signal.get("asset") or signal.get("symbol") or "")
    try:
        instrument = _canonical_instrument(symbol) if symbol else ""
    except Exception:
        instrument = symbol
    candidates = {
        "strategy": _strategy_of(signal),
        "instrument": instrument,
        "asset_class": _asset_class_of(signal, symbol),
    }
    matches = []
    for scope in SCOPES:
        engaged = switches.get(scope) or {}
        value = str(candidates[scope] or "").strip().upper()
        if value and value in engaged:
            matches.append(f"{scope}:{value}")
    return matches


async def execution_block_reason(signal: Mapping[str, Any], *, state: Any = None) -> str | None:
    """Return why execution of ``signal`` is blocked by a scoped switch, or None.

    An unreadable store returns ``scoped_kill_switch_unavailable``: inability to
    establish clearance is itself a block.
    """
    try:
        if state is None:
            from core.redis_state import state as default_state

            state = default_state
        document = await state.get_scoped_killswitches()
    except Exception:
        return UNAVAILABLE
    matches = blocking_switches(document, signal)
    return "scoped_kill_switch:" + ",".join(matches) if matches else None


__all__ = ["SCOPES", "UNAVAILABLE", "apply_change", "blocking_switches", "execution_block_reason", "normalize_key"]
