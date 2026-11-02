"""Prop-firm rule presets and worst-case headroom (2 Nov 2026).

A prop account fails on a single breach, and the breach that ends accounts is
almost never the trade being taken: it is the trade being taken *while other
positions are already open*, each of which can still run to its stop. This
module answers one question before every order: if every open position and the
new order all hit their stops right now, would the account still be above both
of the firm's floors (daily and overall), with a safety buffer to spare?

Pure and deterministic: no broker, database or network calls. Money values are
in account currency; percentages are decimal fractions (0.05 = 5%).

The presets below summarise each firm's published evaluation rules as of the
``verified`` date. Firms change rules; a user confirms the preset against their
own dashboard when linking (``certify_prop_policy``) and can override any value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

D = Decimal

# daily_base: "initial_balance" -> the daily allowance is a % of the initial balance;
#             "day_start_balance" -> a % of the balance at the daily reset.
# The daily floor is always measured from the balance at the daily reset.
# max_loss_mode: "static" -> floor = initial balance - allowance;
#                "trailing_eod" -> floor trails the highest end-of-day balance and,
#                with lock_at_initial, stops rising at the initial balance.
PROP_PRESETS: dict[str, dict[str, Any]] = {
    "ftmo_2step": {
        "firm": "FTMO", "program": "2-Step Challenge / Verification / FTMO Account",
        "daily_loss_pct": "0.05", "daily_base": "initial_balance",
        "max_loss_pct": "0.10", "max_loss_mode": "static",
        "profit_target_pct": {"phase1": "0.10", "phase2": "0.05"}, "min_trading_days": 4,
        "daily_reset_timezone": "Europe/Prague", "daily_reset_time": "00:00",
        "funded_news_blackout_minutes": 2, "funded_weekend_flat": True,
        "source": "https://tradetanto.com/learn/ftmo-rules-evaluation-process", "verified": "2026-06-21",
    },
    "ftmo_1step": {
        "firm": "FTMO", "program": "1-Step Challenge",
        "daily_loss_pct": "0.03", "daily_base": "initial_balance",
        "max_loss_pct": "0.10", "max_loss_mode": "trailing_eod", "lock_at_initial": False,
        "profit_target_pct": {"phase1": "0.10"}, "best_day_max_share": "0.50",
        "daily_reset_timezone": "Europe/Prague", "daily_reset_time": "00:00",
        "funded_news_blackout_minutes": 2, "funded_weekend_flat": True,
        "source": "https://tradetanto.com/learn/ftmo-rules-evaluation-process", "verified": "2026-06-21",
    },
    "fundednext_stellar_2step": {
        "firm": "FundedNext", "program": "Stellar 2-Step",
        "daily_loss_pct": "0.05", "daily_base": "day_start_balance",
        "max_loss_pct": "0.10", "max_loss_mode": "static",
        "profit_target_pct": {"phase1": "0.08", "phase2": "0.05"}, "min_trading_days": 5,
        "daily_reset_timezone": "server", "daily_reset_time": "00:00",
        "source": "https://tradetanto.com/learn/fundednext-rules-a-complete-guide-for-cfd-traders",
        "verified": "2026-07-11",
    },
    "fundednext_stellar_1step": {
        "firm": "FundedNext", "program": "Stellar 1-Step",
        "daily_loss_pct": "0.03", "daily_base": "day_start_balance",
        "max_loss_pct": "0.06", "max_loss_mode": "static",
        "profit_target_pct": {"phase1": "0.10"}, "min_trading_days": 2,
        "daily_reset_timezone": "server", "daily_reset_time": "00:00",
        "source": "https://tradetanto.com/learn/fundednext-rules-a-complete-guide-for-cfd-traders",
        "verified": "2026-07-11",
    },
    "fundednext_stellar_lite": {
        "firm": "FundedNext", "program": "Stellar Lite",
        "daily_loss_pct": "0.04", "daily_base": "day_start_balance",
        "max_loss_pct": "0.08", "max_loss_mode": "static",
        "profit_target_pct": {"phase1": "0.08", "phase2": "0.04"}, "min_trading_days": 5,
        "daily_reset_timezone": "server", "daily_reset_time": "00:00",
        "source": "https://tradetanto.com/learn/fundednext-rules-a-complete-guide-for-cfd-traders",
        "verified": "2026-07-11",
    },
    "fundednext_stellar_instant": {
        "firm": "FundedNext", "program": "Stellar Instant",
        "daily_loss_pct": None, "daily_base": "day_start_balance",
        "max_loss_pct": "0.06", "max_loss_mode": "trailing_eod", "lock_at_initial": True,
        "daily_reset_timezone": "server", "daily_reset_time": "00:00",
        "source": "https://tradetanto.com/learn/fundednext-rules-a-complete-guide-for-cfd-traders",
        "verified": "2026-07-11",
    },
    # Futures: allowances are fixed dollar amounts per account size.
    **{
        f"topstep_{size}k": {
            "firm": "Topstep", "program": f"Trading Combine {size}K",
            "daily_loss_amount": str(daily), "max_loss_amount": str(mll), "max_loss_mode": "trailing_eod",
            "lock_at_initial": True, "profit_target_amount": str(target), "best_day_max_share_of_target": "0.55",
            "max_contracts_minis": minis, "flat_by": "15:10", "flat_by_timezone": "America/Chicago",
            "weekend_flat": True, "daily_reset_timezone": "America/Chicago", "daily_reset_time": "17:00",
            "source": "https://www.futureshive.com/blog/topstep-rules-explained", "verified": "2026-10-05",
        }
        for size, daily, mll, target, minis in ((50, 1000, 2000, 3000, 5), (100, 2000, 3000, 6000, 10),
                                                 (150, 3000, 4500, 9000, 15))
    },
}


def preset(name: str) -> dict[str, Any]:
    key = str(name or "").strip().lower()
    if key not in PROP_PRESETS:
        raise ValueError(f"unknown_prop_preset:{key or 'missing'}")
    return dict(PROP_PRESETS[key])


def list_presets() -> list[dict[str, Any]]:
    return [{"preset": key, **{k: v for k, v in value.items()}} for key, value in sorted(PROP_PRESETS.items())]


@dataclass(frozen=True, slots=True)
class PropAccountState:
    """Account values needed to place both floors. Money in account currency."""

    initial_balance: Decimal
    day_start_balance: Decimal
    current_equity: Decimal
    highest_eod_balance: Decimal = D("0")
    open_risk_amount: Decimal = D("0")  # sum over open positions of loss if each hits its stop
    evaluated_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("initial_balance", "day_start_balance", "current_equity", "highest_eod_balance",
                     "open_risk_amount"):
            object.__setattr__(self, name, D(str(getattr(self, name) or 0)))


@dataclass(frozen=True, slots=True)
class PropHeadroom:
    allowed: bool
    reasons: tuple[str, ...]
    daily_floor: Decimal | None
    max_loss_floor: Decimal | None
    binding_floor: Decimal | None
    room_amount: Decimal  # loss the account can still absorb (after buffer and open risk)
    max_new_risk_pct: Decimal  # of current equity

    def as_dict(self) -> dict[str, Any]:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in
                {"allowed": self.allowed, "reasons": list(self.reasons), "daily_floor": self.daily_floor,
                 "max_loss_floor": self.max_loss_floor, "binding_floor": self.binding_floor,
                 "room_amount": self.room_amount, "max_new_risk_pct": self.max_new_risk_pct}.items()}


def _amount(rules: Mapping[str, Any], pct_key: str, amount_key: str, base: Decimal) -> Decimal | None:
    if rules.get(amount_key) not in (None, ""):
        return D(str(rules[amount_key]))
    if rules.get(pct_key) not in (None, ""):
        return D(str(rules[pct_key])) * base
    return None


def floors(rules: Mapping[str, Any], state: PropAccountState) -> tuple[Decimal | None, Decimal | None]:
    """Equity levels the firm must never see: (daily floor, overall floor)."""
    initial = state.initial_balance
    daily_base = initial if rules.get("daily_base", "initial_balance") == "initial_balance" else state.day_start_balance
    daily_allowance = _amount(rules, "daily_loss_pct", "daily_loss_amount", daily_base)
    daily_floor = state.day_start_balance - daily_allowance if daily_allowance is not None else None
    max_allowance = _amount(rules, "max_loss_pct", "max_loss_amount", initial)
    max_floor = None
    if max_allowance is not None:
        if rules.get("max_loss_mode", "static") == "trailing_eod":
            peak = max(state.highest_eod_balance, initial)
            max_floor = peak - max_allowance
            if rules.get("lock_at_initial"):
                max_floor = min(max_floor, initial)
        else:
            max_floor = initial - max_allowance
    return daily_floor, max_floor


def _in_flat_window(rules: Mapping[str, Any], when: datetime, minutes_before: int) -> bool:
    raw = str(rules.get("flat_by") or "")
    if not raw:
        return False
    zone = ZoneInfo(str(rules.get("flat_by_timezone") or "UTC"))
    local = when.astimezone(zone)
    hh, mm = (int(x) for x in raw.split(":"))
    flat = datetime.combine(local.date(), time(hh, mm), tzinfo=zone)
    reset_raw = str(rules.get("daily_reset_time") or "")
    reopen = None
    if reset_raw and str(rules.get("daily_reset_timezone") or "") == str(rules.get("flat_by_timezone") or ""):
        rh, rm = (int(x) for x in reset_raw.split(":"))
        reopen = datetime.combine(local.date(), time(rh, rm), tzinfo=zone)
    if flat - timedelta(minutes=minutes_before) <= local < flat:
        return True
    # between the forced flat time and the next session open nothing may be opened
    return bool(reopen and flat <= local < reopen)


def evaluate_headroom(
    rules: Mapping[str, Any],
    state: PropAccountState,
    *,
    proposed_risk_amount: Decimal | float | str = 0,
    safety_buffer_pct: Decimal | float | str = "0.005",
    flat_window_minutes: int = 30,
    weekend_hold_expected: bool = False,
    high_impact_news_window: bool = False,
    funded: bool = False,
) -> PropHeadroom:
    """Fail-closed admission for one new order on a prop account."""
    reasons: list[str] = []
    proposed = D(str(proposed_risk_amount or 0))
    buffer = D(str(safety_buffer_pct or 0)) * state.initial_balance
    if state.initial_balance <= 0 or state.day_start_balance <= 0 or state.current_equity <= 0:
        return PropHeadroom(False, ("prop_baseline_unavailable",), None, None, None, D("0"), D("0"))
    daily_floor, max_floor = floors(rules, state)
    candidates = [f for f in (daily_floor, max_floor) if f is not None]
    binding = max(candidates) if candidates else None
    if binding is None:
        reasons.append("prop_rules_have_no_floor")
        room = D("0")
    else:
        guard = binding + buffer
        if daily_floor is not None and state.current_equity <= daily_floor + buffer:
            reasons.append("prop_daily_floor_reached")
        if max_floor is not None and state.current_equity <= max_floor + buffer:
            reasons.append("prop_max_loss_floor_reached")
        room = state.current_equity - state.open_risk_amount - guard
        if room <= 0:
            reasons.append("prop_open_risk_uses_all_headroom")
        elif proposed > room:
            reasons.append("prop_worst_case_would_breach")
    if proposed <= 0:
        reasons.append("prop_order_risk_unknown")
    if _in_flat_window(rules, state.evaluated_at_utc, flat_window_minutes):
        reasons.append("prop_flat_by_window")
    weekend_flat = bool(rules.get("weekend_flat") or (funded and rules.get("funded_weekend_flat")))
    if weekend_hold_expected and weekend_flat:
        reasons.append("prop_weekend_holding_forbidden")
    if high_impact_news_window and funded and int(rules.get("funded_news_blackout_minutes") or 0) > 0:
        reasons.append("prop_news_blackout")
    max_new = max(D("0"), room) / state.current_equity if state.current_equity > 0 else D("0")
    return PropHeadroom(not reasons, tuple(dict.fromkeys(reasons)), daily_floor, max_floor, binding,
                        max(D("0"), room), max_new.quantize(D("0.000001")))


def open_risk_amount(positions: Iterable[Mapping[str, Any]], *, equity: Decimal,
                     fallback_risk_pct: Decimal) -> tuple[Decimal, int]:
    """Loss if every open position hits its stop now. Returns (amount, positions without a usable stop).

    A position's money-per-price-unit is taken from its own unrealised profit
    and price move. When that cannot be derived, or the position has no stop,
    it is charged ``fallback_risk_pct`` of equity (callers pass the account's
    maximum risk per trade), so unknown exposure is never counted as zero.
    """
    total, unknown = D("0"), 0
    for pos in positions or []:
        try:
            current = D(str(pos.get("currentPrice") or pos.get("current_price") or 0))
            opened = D(str(pos.get("openPrice") or pos.get("open_price") or 0))
            stop = D(str(pos.get("stopLoss") or pos.get("stop_loss") or 0))
            profit = D(str(pos.get("unrealizedProfit") if pos.get("unrealizedProfit") is not None
                           else pos.get("profit") or 0))
        except Exception:
            current = opened = stop = profit = D("0")
        per_unit = abs(profit / (current - opened)) if current > 0 and opened > 0 and current != opened else D("0")
        if stop > 0 and current > 0 and per_unit > 0:
            side = str(pos.get("type") or pos.get("side") or "").lower()
            is_long = "buy" in side or "long" in side
            distance = (current - stop) if is_long else (stop - current)
            total += max(D("0"), distance) * per_unit
        else:
            unknown += 1
            total += fallback_risk_pct * equity
    return total, unknown


def policy_fields_from_preset(
    name: str,
    *,
    initial_balance: Decimal | float | str,
    phase: str | None = None,
    funded: bool = False,
    safety_buffer_pct: Decimal | float | str = "0.005",
) -> dict[str, Any]:
    """Keyword arguments for ``configure_account_policy`` that encode a firm preset.

    Dollar allowances (futures firms) are converted to fractions of the initial
    balance for the generic limits; the ``prop_preset`` hard rule keeps the exact
    money floors. Internal ceilings are set equal to the firm's limits, and the
    safety buffer keeps SignalRank inside them.
    """
    rules = preset(name)
    initial = D(str(initial_balance))
    if initial <= 0:
        raise ValueError("invalid_initial_balance")

    def fraction(pct_key: str, amount_key: str) -> Decimal | None:
        if rules.get(amount_key) not in (None, ""):
            return (D(str(rules[amount_key])) / initial).quantize(D("0.0001"))
        if rules.get(pct_key) not in (None, ""):
            return D(str(rules[pct_key]))
        return None

    daily = fraction("daily_loss_pct", "daily_loss_amount")
    overall = fraction("max_loss_pct", "max_loss_amount")
    if overall is None:
        raise ValueError("preset_without_max_loss")
    buffer = D(str(safety_buffer_pct))
    weekend_flat = bool(rules.get("weekend_flat") or (funded and rules.get("funded_weekend_flat")))
    news_blocked = bool(funded and int(rules.get("funded_news_blackout_minutes") or 0) > 0)
    return {
        "account_mode": "PROP",
        "prop_firm": rules["firm"],
        "prop_phase": phase or ("funded" if funded else "evaluation"),
        "prop_rules_version": f"{name}@{rules['verified']}",
        # A firm without a daily limit still gets SignalRank's own 5% ceiling.
        "external_max_daily_loss_pct": daily if daily is not None else D("0.05"),
        "external_max_total_drawdown_pct": overall,
        "max_daily_loss_pct": daily if daily is not None else D("0.05"),
        "max_total_drawdown_pct": overall,
        "safety_buffer_pct": buffer,
        "news_trading_allowed": not news_blocked,
        "weekend_holding_allowed": not weekend_flat,
        "external_rules": {
            "hard_rules": [{
                "id": "firm_preset", "type": "prop_preset", "preset": name, "initial_balance": str(initial),
                "funded": bool(funded), "safety_buffer_pct": str(buffer),
            }],
        },
    }


__all__ = [
    "PROP_PRESETS",
    "policy_fields_from_preset",
    "PropAccountState",
    "PropHeadroom",
    "evaluate_headroom",
    "floors",
    "list_presets",
    "open_risk_amount",
    "preset",
]
