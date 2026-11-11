"""Gate exemptions backed by tracked outcomes (owner request, 11 Nov 2026).

A quality gate is kept unless the setups it rejected would clearly have made money.
Tracked outcomes of rejected setups (decision_log ML layer, ids 4.6M-5.1M, one row
per asset/timeframe/direction/strategy/hour) showed, for crypto on 1h only:

* weak-trend chop veto: 77 setups, 75 % reached TP1 vs 29 % break-even, +1.60R;
* ADX floor: 69 setups, 61 % vs 29 %, +1.16R;
* confluence floor: 31 setups, 74 % vs 27 %, +1.89R.

The same gates were right elsewhere (crypto 5m negative, crypto 15m not
significant, FX multi-timeframe and FX ADX clearly negative), so only these
(gate, class, timeframe) cells are exempt. Every other check, the setup-evidence
filter and the Ultra 80 floor still apply to them.

``QUALITY_GATE_EVIDENCE_EXEMPTIONS`` overrides the list ("gate:class:tf,...";
"none" disables all exemptions).
"""
from __future__ import annotations

import os

DEFAULT_EXEMPTIONS = "weak_trend:crypto:1h,quality_adx:crypto:1h,quality_confluence:crypto:1h"


def _cells() -> set[tuple[str, str, str]]:
    raw = str(os.getenv("QUALITY_GATE_EVIDENCE_EXEMPTIONS", DEFAULT_EXEMPTIONS) or "").strip()
    if raw.lower() in {"", "none", "off", "0"}:
        return set()
    out = set()
    for item in raw.split(","):
        parts = [p.strip().lower() for p in item.split(":")]
        if len(parts) == 3 and all(parts):
            out.add((parts[0], parts[1], parts[2]))
    return out


def asset_class_of(asset: str) -> str:
    try:
        from core.asset_class_key import canonical_asset_class

        return str(canonical_asset_class(asset) or "").lower()
    except Exception:
        return ""


def exempt(gate: str, asset_class: str, timeframe: str) -> bool:
    cls = str(asset_class or "").lower()
    cls = {"forex": "fx", "cryptocurrency": "crypto", "commodities": "commodity"}.get(cls, cls)
    return (str(gate).lower(), cls, str(timeframe or "").strip().lower()) in _cells()
