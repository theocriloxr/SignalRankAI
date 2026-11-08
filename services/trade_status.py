"""One description of where a delivered signal stands, and what it has made.

Owner findings, 8 Nov 2026:
1. "A trade that has triggered its entry will continue to show waiting for
   entry." The web list labelled signals from ``outcomes.status``; that
   projection stays ``pending`` after entry while ``signal_lifecycles.state``
   is ``ACTIVE_TRADE``/``TP1_HIT``. The Telegram position view guessed "awaiting
   entry" from the distance between price and entry.
2. "Closed signals don't show the balance of the trade or the P/L."

The lifecycle state is the authority here (the outcome tracker writes it
first); the outcome row decides only when no lifecycle row exists. Realized R
for a protected exit uses ``core.partial_exit_accounting``, the same rule the
ledger books. This module only reads; it never writes outcomes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

_LIFECYCLE = {
    "WATCHING_FOR_ENTRY": ("waiting_for_entry", "Waiting for entry", "info", False, False),
    "ACTIVE_TRADE": ("open", "Entry triggered — trade open", "info", True, False),
    "TP1_HIT": ("open_tp1", "TP1 hit — stop protected at entry", "positive", True, False),
    "TP2_HIT": ("open_tp2", "TP2 hit — stop protected at entry", "positive", True, False),
    "TP3_HIT": ("closed_tp3", "Closed at the final target", "positive", True, True),
    "SL_HIT": ("closed_sl", "Closed at the stop", "negative", True, True),
    "BREAKEVEN_STOP": ("closed_protected", "Closed at the protected stop after a target", "positive", True, True),
    "MISSED_ENTRY": ("closed_no_entry", "Entry never reached — no trade", "neutral", False, True),
    "EXPIRED": ("closed_expired", "Expired", "neutral", False, True),
    "CLOSED_TIME_STOP": ("closed_time", "Closed at the time limit", "neutral", True, True),
}

_OUTCOME = {
    "pending": "WATCHING_FOR_ENTRY", "pending_entry": "WATCHING_FOR_ENTRY", "": "WATCHING_FOR_ENTRY",
    "active": "ACTIVE_TRADE", "open": "ACTIVE_TRADE",
    "tp1": "TP1_HIT", "tp2": "TP2_HIT", "tp3": "TP3_HIT", "tp": "TP3_HIT", "win": "TP3_HIT",
    "sl": "SL_HIT", "loss": "SL_HIT",
    "partial_win_be": "BREAKEVEN_STOP", "partial_win": "BREAKEVEN_STOP",
    "missed_entry": "MISSED_ENTRY", "missed": "MISSED_ENTRY", "not_triggered": "MISSED_ENTRY",
    "expired": "EXPIRED", "time_stop": "CLOSED_TIME_STOP",
}

_HIGHEST_TP = {"TP1_HIT": 1, "TP2_HIT": 2, "TP3_HIT": 3}


@dataclass(frozen=True)
class TradeStatus:
    code: str
    label: str
    tone: str
    entry_triggered: bool
    closed: bool
    highest_tp: int
    source: str
    realized_r: float | None
    realized_pct: float | None
    banked_r: float | None
    open_share: float | None
    result_per_100_risk: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _banked(entry: Any, stop: Any, take_profit: Any, direction: Any, highest_tp: int) -> tuple[float | None, float | None]:
    """R already locked in by the planned partial closes, and the share still open."""
    if highest_tp <= 0:
        return None, None
    try:
        from core.partial_exit_accounting import calculate_partial_exit_result, planned_exit_fractions
    except Exception:
        return None, None
    f1, f2, _runner = planned_exit_fractions()
    stage = min(highest_tp, 2)
    result = calculate_partial_exit_result(entry=entry, stop_loss=stop, take_profit=take_profit,
                                           direction=direction, highest_tp=stage)
    if result is None:
        return None, None
    return float(result.realized_r), max(0.0, 1.0 - f1 - (f2 if stage >= 2 else 0.0))


def describe_trade(
    *,
    lifecycle_state: Any = None,
    outcome_status: Any = None,
    canonical_outcome: Any = None,
    r_multiple: Any = None,
    pnl_pct: Any = None,
    highest_tp_hit: Any = None,
    entry: Any = None,
    stop_loss: Any = None,
    take_profit: Any = None,
    direction: Any = None,
) -> TradeStatus:
    state = str(lifecycle_state or "").strip().upper()
    source = "lifecycle"
    if state not in _LIFECYCLE:
        status = str(outcome_status or "").strip().lower()
        state = _OUTCOME.get(status) or _OUTCOME.get(str(canonical_outcome or "").strip().lower(), "")
        source = "outcome" if state else "none"
    if state not in _LIFECYCLE:
        state = "WATCHING_FOR_ENTRY"
    code, label, tone, triggered, closed = _LIFECYCLE[state]
    try:
        highest = max(_HIGHEST_TP.get(state, 0), int(highest_tp_hit or 0))
    except (TypeError, ValueError):
        highest = _HIGHEST_TP.get(state, 0)
    realized_r = _float(r_multiple) if closed and triggered else None
    realized_pct = _float(pnl_pct) if closed and triggered else None
    if state == "SL_HIT" and highest > 0:
        # A stop after a target is a protected exit under the published plan.
        code, label, tone = "closed_protected", "Closed at the protected stop after a target", "positive"
    banked_r, open_share = (None, None)
    if not closed and highest > 0:
        banked_r, open_share = _banked(entry, stop_loss, take_profit, direction, highest)
    basis = realized_r if realized_r is not None else banked_r
    return TradeStatus(
        code=code, label=label, tone=tone, entry_triggered=bool(triggered), closed=bool(closed),
        highest_tp=int(highest), source=source,
        realized_r=None if realized_r is None else round(realized_r, 4),
        realized_pct=None if realized_pct is None else round(realized_pct, 4),
        banked_r=None if banked_r is None else round(banked_r, 4),
        open_share=None if open_share is None else round(open_share, 4),
        result_per_100_risk=None if basis is None else round(basis * 100.0, 2),
    )


def trade_status_line(status: TradeStatus) -> str:
    """Plain one-line summary for Telegram."""
    parts = [status.label]
    if status.realized_r is not None:
        money = f" (${status.result_per_100_risk:+,.2f} per $100 risked)" if status.result_per_100_risk is not None else ""
        pct = f", {status.realized_pct:+.2f}% price move" if status.realized_pct is not None else ""
        parts.append(f"result {status.realized_r:+.2f}R{money}{pct}")
    elif status.banked_r is not None:
        share = f"; {status.open_share:.0%} still open with the stop at entry" if status.open_share else ""
        parts.append(f"{status.banked_r:+.2f}R banked by the planned close{share}")
    elif status.closed and not status.entry_triggered:
        parts.append("no position, no P/L")
    return " — ".join(parts)
