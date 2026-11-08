"""Current-state banner for a signal card opened again after delivery.

Owner report, 4 Nov 2026: the SUIUSDT 5m card opened from the "TP1 HIT"
message at 14:53 and 14:54 UTC+1 read like a fresh signal ("Execution: Manual
— confirm trade and size yourself", "Expires: 17h 3m") although TP1 had been
hit at 09:36 and the stop was protected at entry. A reopened card now starts
with what has already happened, from the lifecycle and outcome records.
"""
from __future__ import annotations

from typing import Any

_TERMINAL_TEXT = {
    "TP3_HIT": "closed at the final target",
    "SL_HIT": "closed at the stop",
    "BREAKEVEN_STOP": "closed at the protected stop (entry) after a target",
    "MISSED_ENTRY": "closed: the entry was never reached",
    "EXPIRED": "expired",
    "CLOSED_TIME_STOP": "closed at the time limit",
}


def signal_status_banner(state: Any, *, highest_tp: int = 0, realized_r: Any = None) -> str | None:
    """One line describing the signal now, or None while it still awaits entry."""
    value = str(state or "").strip().upper()
    if not value or value == "WATCHING_FOR_ENTRY":
        return None
    r_text = ""
    try:
        if realized_r is not None:
            r_text = f" ({float(realized_r):+.2f}R)"
    except (TypeError, ValueError):
        r_text = ""
    if value in _TERMINAL_TEXT:
        return f"📌 <b>Status now:</b> {_TERMINAL_TEXT[value]}{r_text}. This is not a new entry."
    if value == "ACTIVE_TRADE":
        return "📌 <b>Status now:</b> entry was triggered; the trade is open. This is not a new entry."
    if value in {"TP1_HIT", "TP2_HIT"}:
        stage = highest_tp if highest_tp > 0 else int(value[2])
        return (f"📌 <b>Status now:</b> TP{stage} already hit; the stop is protected at entry. "
                "This is not a new entry.")
    return f"📌 <b>Status now:</b> {value.replace('_', ' ').lower()}. This is not a new entry."
