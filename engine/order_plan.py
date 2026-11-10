"""Order type and pip/risk breakdown for a signal (owner request, 10 Nov 2026).

"Add the type of trade / pending order to take (buy limit, sell limit, market,
buy stop, sell stop, buy stop limit, sell stop limit) and show how many pips a
trade is, with the breakdown: total risk = stop loss (pips) × pip value × lots."

Order type, from where price stands when the signal is read:

* at the entry (within ``ORDER_PLAN_MARKET_BAND_R`` × risk, default 0.1R): market order;
* long, entry below price: Buy Limit (wait for the pullback);
* long, entry above price: Buy Stop (wait for the breakout), with a Buy Stop
  Limit alternative whose limit caps slippage at ``ORDER_PLAN_STOP_LIMIT_R``
  (default 0.1R) beyond the trigger;
* short: Sell Limit / Sell Stop / Sell Stop Limit, mirrored.

Pips use the standard retail conventions, stated on the card because brokers
differ: FX 0.0001 (JPY pairs 0.01), gold 0.1, silver 0.01, oil 0.01, indices
1 point, stocks 0.01, crypto 1 unit of price. Pip value per 1.00 lot uses the
usual contract sizes (FX 100,000; gold 100 oz; silver 5,000 oz; oil 1,000 bbl;
indices and crypto 1 unit; stocks 1 share). It is in USD when the quote
currency is USD (or the base is USD, converted at the entry price); otherwise it
is given in the quote currency and the lot count is left to the trader.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

_METALS = {"XAUUSD": (0.1, 100.0), "XAGUSD": (0.01, 5000.0), "XPTUSD": (0.1, 100.0), "XPDUSD": (0.1, 100.0)}
_ENERGY = {"WTI": (0.01, 1000.0), "USOIL": (0.01, 1000.0), "BRENT": (0.01, 1000.0), "UKOIL": (0.01, 1000.0),
           "NATGAS": (0.001, 10000.0)}
_INDICES = {"US30", "NAS100", "US100", "US500", "SPX500", "GER40", "DE40", "UK100", "JP225", "JPN225", "AUS200",
            "FRA40", "EU50", "HK50"}
_FIAT = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "SEK", "NOK", "DKK", "SGD", "HKD", "ZAR", "MXN",
         "TRY", "PLN", "HUF", "CZK", "CNH"}


def _env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class PipSpec:
    pip: float
    contract: float
    unit: str            # "pips" or "points"
    quote: str           # currency the pip value is first expressed in
    note: str


def pip_spec(asset: str) -> PipSpec:
    a = str(asset or "").upper().replace("/", "").replace("-", "").strip()
    if a in _METALS:
        pip, contract = _METALS[a]
        return PipSpec(pip, contract, "pips", "USD", f"{a[:3]} pip {pip:g}, 1 lot = {contract:g} oz")
    if a in _ENERGY:
        pip, contract = _ENERGY[a]
        return PipSpec(pip, contract, "pips", "USD", f"oil pip {pip:g}, 1 lot = {contract:g} units")
    if a in _INDICES:
        return PipSpec(1.0, 1.0, "points", "USD" if a.startswith(("US", "NAS", "SPX")) else "", "index: 1 point, 1 lot = 1 contract")
    if a.endswith(("USDT", "USDC", "USD")) and not (len(a) == 6 and a[:3] in _FIAT):
        return PipSpec(1.0, 1.0, "points", "USD", "crypto: 1 point = 1.00 of price, 1 lot = 1 coin")
    if len(a) == 6 and a[:3] in _FIAT and a[3:] in _FIAT:
        pip = 0.01 if a[3:] == "JPY" else 0.0001
        return PipSpec(pip, 100000.0, "pips", a[3:], f"FX pip {pip:g}, 1 lot = 100,000 {a[:3]}")
    return PipSpec(0.01, 1.0, "points", "USD", "stock: 1 point = 0.01, 1 lot = 1 share")


def order_type(direction: str, entry: float, current: Optional[float], risk: float) -> dict[str, Any]:
    long_side = str(direction or "").strip().lower() in {"long", "buy", "bullish"}
    side = "Buy" if long_side else "Sell"
    band = max(0.0, _env("ORDER_PLAN_MARKET_BAND_R", 0.1)) * risk
    if current is None or current <= 0 or abs(current - entry) <= band:
        return {"type": f"{side} (market)", "why": "price is at the entry", "alternative": None}
    above = entry > current
    if long_side:
        kind, why = ("Buy Stop", "entry is above the price: it fills on the breakout") if above else \
                    ("Buy Limit", "entry is below the price: it fills on the pullback")
    else:
        kind, why = ("Sell Limit", "entry is above the price: it fills on the rally") if above else \
                    ("Sell Stop", "entry is below the price: it fills on the breakdown")
    alternative = None
    if kind.endswith("Stop"):
        cap = max(0.0, _env("ORDER_PLAN_STOP_LIMIT_R", 0.1)) * risk
        limit = entry + cap if long_side else entry - cap
        alternative = {"type": f"{kind} Limit", "trigger": entry, "limit": limit,
                       "why": "same trigger, but it never fills worse than the limit"}
    return {"type": kind, "why": why, "alternative": alternative}


def build_order_plan(signal: Mapping[str, Any], *, risk_amount: Optional[float] = None) -> Optional[dict[str, Any]]:
    try:
        entry = float(signal.get("entry"))
        stop = float(signal.get("stop_loss") or signal.get("stop"))
    except (TypeError, ValueError):
        return None
    risk = abs(entry - stop)
    if entry <= 0 or risk <= 0:
        return None
    asset = str(signal.get("asset") or signal.get("symbol") or "")
    spec = pip_spec(asset)
    raw_tp = signal.get("take_profit") or signal.get("targets") or []
    targets = [float(t) for t in (raw_tp if isinstance(raw_tp, (list, tuple)) else [raw_tp]) if _num(t)]
    current = _num(signal.get("current_price") or signal.get("live_price"))
    stop_pips = risk / spec.pip
    pip_value = spec.pip * spec.contract  # in the quote currency, per 1.00 lot
    pip_value_usd: Optional[float] = None
    if spec.quote == "USD":
        pip_value_usd = pip_value
    elif len(asset.replace("/", "")) == 6 and asset.upper().startswith("USD"):
        pip_value_usd = pip_value / entry  # e.g. USDJPY: ¥1,000 per lot ÷ price
    if risk_amount is None:
        size = _num(signal.get("suggested_position_size") or signal.get("position_size"))
        risk_amount = size * risk if size else _env("ORDER_PLAN_DEFAULT_RISK_USD", 50.0)
    lots = (risk_amount / (stop_pips * pip_value_usd)) if pip_value_usd else None
    return {
        "asset": asset,
        "order": order_type(str(signal.get("direction") or "long"), entry, current, risk),
        "unit": spec.unit,
        "pip_size": spec.pip,
        "stop_pips": stop_pips,
        "target_pips": [abs(t - entry) / spec.pip for t in targets],
        "pip_value_per_lot": pip_value,
        "pip_value_currency": spec.quote or "quote currency",
        "pip_value_usd": pip_value_usd,
        "risk_amount": risk_amount,
        "lots": lots,
        "check": (stop_pips * pip_value_usd * lots) if lots else None,
        "convention": spec.note,
    }


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def order_plan_lines(signal: Mapping[str, Any], fmt=lambda v: f"{v:,.5g}") -> list[str]:
    """Card lines (Telegram, email) for the order type and the pip/risk breakdown."""
    plan = build_order_plan(signal)
    if not plan:
        return []
    order = plan["order"]
    lines = [f"🧾 Order type: {order['type']} at {fmt(float(signal.get('entry')))} ({order['why']})"]
    alt = order.get("alternative")
    if alt:
        lines.append(f"   or {alt['type']}: trigger {fmt(alt['trigger'])}, limit {fmt(alt['limit'])} ({alt['why']})")
    unit = plan["unit"]
    tp = " • ".join(f"TP{i} {p:,.1f}" for i, p in enumerate(plan["target_pips"][:3], 1))
    lines.append(f"📏 Distance: stop {plan['stop_pips']:,.1f} {unit}" + (f" • {tp} {unit}" if tp else ""))
    if plan["lots"]:
        lines.append(
            f"🧮 Risk = stop ({plan['stop_pips']:,.1f} {unit}) × {unit[:-1]} value (${plan['pip_value_usd']:,.2f} per 1.00 lot)"
            f" × lots ({plan['lots']:,.2f}) = ${plan['check']:,.2f}")
        lines.append(f"   Lots for ${plan['risk_amount']:,.2f} risk = {plan['risk_amount']:,.2f} ÷ "
                     f"({plan['stop_pips']:,.1f} × {plan['pip_value_usd']:,.2f}) = {plan['lots']:,.2f}")
    else:
        lines.append(f"🧮 Risk = stop ({plan['stop_pips']:,.1f} {unit}) × {unit[:-1]} value "
                     f"({plan['pip_value_per_lot']:,.2f} {plan['pip_value_currency']} per 1.00 lot) × lots; "
                     "convert the pip value to your account currency first")
    lines.append(f"   Assumes {plan['convention']}; check the contract size in your platform.")
    return lines
