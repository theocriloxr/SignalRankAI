"""Conservative signal advice; venue specifications remain broker authority."""
from collections.abc import Mapping
import math
from typing import Any

from core.tier_constants import DD_HARD_LIMIT, DD_SOFT_THROTTLE
from engine.signal_metrics import resolve_calibrated_probability


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def account_drawdown(state: Any) -> float | None:
    value = state.get("drawdown") if isinstance(state, Mapping) else getattr(state, "drawdown", None)
    number = finite_number(value)
    return number if number is not None and number >= 0 else None


def bounded_risk_percent(signal: dict[str, Any], *, base: Any, probability_base: Any,
                         probability_range: Any, account_state: Any = None) -> float:
    """Heuristics may reduce risk, never increase the configured base budget."""
    base, weight_base, weight_range = finite_number(base), finite_number(probability_base), finite_number(probability_range)
    if (base is None or not 0 <= base <= 1.25 or weight_base is None or weight_range is None
            or not 0 <= weight_base <= 1 or not 0 <= weight_range <= 1 or weight_base + weight_range > 1):
        return 0.0
    probability = resolve_calibrated_probability(signal)
    if signal.get("ml_calibration_validated") is True and probability is None:
        return 0.0
    sentiment = finite_number(signal.get("news_sentiment") if signal.get("news_sentiment") is not None else signal.get("gemini_score", 0))
    expectancy = finite_number(signal["live_expectancy"]) if "live_expectancy" in signal else None
    if sentiment is None or ("live_expectancy" in signal and expectancy is None):
        return 0.0
    direction = signal.get("direction")
    if direction is not None and (not isinstance(direction, str) or direction.lower().strip() not in {"", "long", "buy", "short", "sell"}):
        return 0.0
    side = str(direction or "").lower().strip()
    model_weight = weight_base + probability * weight_range if probability is not None else 1.0
    regime_weight = 1.2 if signal.get("regime") == "trending" else 0.8 if signal.get("regime") == "ranging" else 1.0
    sentiment_weight = 0.7 if abs(sentiment) > 2 else 1.1 if sentiment * (1 if side in {"long", "buy"} else -1) > 1 else 1.0
    # Expectancy in R and account drawdown fractions are different units.
    # Positive expectancy does not grant additional capital without approval.
    expectancy_weight = 0.5 if expectancy is not None and expectancy <= 0 else 1.0
    percentage = min(base, base * model_weight * regime_weight * sentiment_weight * expectancy_weight)
    if account_state is not None:
        drawdown = account_drawdown(account_state)
        if drawdown is None or drawdown >= DD_HARD_LIMIT:
            return 0.0
        if drawdown > DD_SOFT_THROTTLE:
            percentage *= 0.5
    return percentage if math.isfinite(percentage) and percentage > 0 else 0.0


def bounded_spot_units(*, equity: Any, entry: Any, stop: Any, risk_amount: Any,
                       notional_budget: Any, direction: Any = None) -> float:
    """Return spot units bounded by quote loss and notional budgets, no floors."""
    values = [finite_number(value) for value in (equity, entry, stop, risk_amount, notional_budget)]
    if any(value is None or value <= 0 for value in values):
        return 0.0
    equity_value, entry_value, stop_value, loss_budget, quote_budget = values
    assert equity_value is not None and entry_value is not None and stop_value is not None and loss_budget is not None and quote_budget is not None
    side = str(direction or "").lower().strip()
    distance = abs(entry_value - stop_value)
    if (distance <= 0 or (side in {"long", "buy"} and stop_value >= entry_value)
            or (side in {"short", "sell"} and stop_value <= entry_value)
            or (side and side not in {"long", "buy", "short", "sell"})):
        return 0.0
    units = min(loss_budget / distance, quote_budget / entry_value)
    if not math.isfinite(units) or units <= 0:
        return 0.0
    if units * distance > loss_budget or units * entry_value > quote_budget:
        units = math.nextafter(units, 0.0)
    return units if units > 0 and units * distance <= loss_budget and units * entry_value <= quote_budget else 0.0
