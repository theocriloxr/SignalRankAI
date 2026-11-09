"""Focus scanning on the instruments a user's prop firm/broker offers (owner request, 9 Nov 2026).

"I am now using my FundedNext account and I want it to focus more on the assets
FundedNext provides." Unlike ``core.focused_universe`` (a staging-only scan
boundary), this only re-orders and tops up the production scan list: broker
instruments are scanned first every cycle and are always included; other
assets keep their place behind them unless ``BROKER_UNIVERSE_STRICT`` is on.
It never changes execution permissions.

``BROKER_UNIVERSE_PROFILE`` selects the profile (default ``fundednext``; ``off``
disables). ``BROKER_UNIVERSE_ASSETS`` overrides the list.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable

_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "broker_universes.json"


@lru_cache(maxsize=1)
def _profiles() -> dict:
    try:
        return dict(json.loads(_CONFIG.read_text("utf-8")).get("profiles") or {})
    except Exception:
        return {}


def _canonical(symbol: str) -> str:
    try:
        from services.asset_mapper import canonicalize_symbol

        return str(canonicalize_symbol(symbol) or symbol).upper().strip()
    except Exception:
        return str(symbol).upper().strip()


def active_profile() -> str:
    name = str(os.getenv("BROKER_UNIVERSE_PROFILE", "fundednext") or "").strip().lower()
    return "" if name in {"", "off", "none", "0", "false"} else name


def profile_label() -> str:
    name = active_profile()
    return str((_profiles().get(name) or {}).get("label") or name.title()) if name else ""


def broker_assets() -> tuple[str, ...]:
    name = active_profile()
    if not name:
        return ()
    override = [s.strip() for s in str(os.getenv("BROKER_UNIVERSE_ASSETS") or "").split(",") if s.strip()]
    raw = override or list((_profiles().get(name) or {}).get("assets") or [])
    return tuple(dict.fromkeys(_canonical(s) for s in raw))


def is_broker_asset(symbol: str) -> bool:
    return bool(symbol) and _canonical(symbol) in set(broker_assets())


def prioritize(assets: Iterable[str]) -> list[str]:
    """Broker instruments first (all of them), then the rest unless strict."""
    current = [str(a) for a in assets]
    focus = broker_assets()
    if not focus:
        return current
    present = {_canonical(a): a for a in current}
    first = [present.get(symbol, symbol) for symbol in focus]
    if str(os.getenv("BROKER_UNIVERSE_STRICT", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        return first
    chosen = set(first)
    return first + [a for a in current if a not in chosen]
