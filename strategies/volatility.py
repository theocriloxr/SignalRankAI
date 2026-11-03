import logging

from data.indicator_schema import missing_indicators, normalize_indicator_schema
from .base import BaseStrategy

logger = logging.getLogger(__name__)


def _breakout_levels(candles, ind):
    """BUY levels at the last close: stop at the bar's low, target 2R.

    A bar that closes at its low put the stop on the entry (production, 3 Nov:
    LINKUSDT 1d 11.005/11.005, 342 rejections a day). When the low is missing,
    on the wrong side or inside 0.25 ATR of entry, use the platform's ATR rule
    (core.atr_levels) instead; no levels at all when the ATR is unknown.
    """
    from core import atr_levels as levels

    entry = float(candles[-1]["close"])
    stop = candles[-1].get("low")
    highs, lows, closes = levels.ohlc(candles)
    try:
        atr_value = float(ind.get("atr") or 0) or None
    except (TypeError, ValueError):
        atr_value = None
    atr_value = atr_value or levels.atr(highs, lows, closes)
    if atr_value is None:
        return None
    if not levels.stop_is_degenerate("long", entry, stop, atr_value):
        stop = float(stop)
        return entry, stop, entry + (entry - stop) * 2
    rebuilt = levels.atr_levels("long", entry, highs, lows, atr_value) if lows else None
    if rebuilt is None:
        return None
    stop, targets = rebuilt
    return entry, stop, targets


# --- Volatility Strategies ---
class ATRBreakoutStrategy(BaseStrategy):
    name = "ATR Breakout"

    def evaluate(self, market_data):
        ind = normalize_indicator_schema(market_data.get("indicators") or {})
        candles = market_data.get("candles") or []
        bollinger = ind.get("bollinger") if isinstance(ind.get("bollinger"), dict) else {}
        width = bollinger.get("width") or ind.get("bollinger_width")
        missing = missing_indicators(ind, ("atr",))
        if width in (None, ""):
            missing.append("bollinger.width")
        if not candles or missing:
            logger.debug(
                "%s missing indicators: %s available=%s",
                self.name,
                missing,
                sorted(ind.keys())[:12],
            )
            return None
        atr = float(ind.get("atr") or 0)
        width_f = float(width or 0)
        if atr > 1.5 * width_f and candles:
            levels = _breakout_levels(candles, ind)
            if levels is None:
                return None
            entry, stop, target = levels
            return {
                "direction": "BUY",
                "entry": entry,
                "stop": stop,
                "targets": target,
                "confidence": 0.8,
                "reasoning": "ATR breakout: ATR > 1.5x Bollinger width. Volatility surge for BUY.",
            }
        return None


class BBWidthVolatilityStrategy(BaseStrategy):
    name = "BB Width Volatility"

    def evaluate(self, market_data):
        ind = normalize_indicator_schema(market_data.get("indicators") or {})
        candles = market_data.get("candles") or []
        if ind.get("bollinger_width", 0) > 0.05 and candles:
            levels = _breakout_levels(candles, ind)
            if levels is None:
                return None
            entry, stop, target = levels
            return {
                "direction": "BUY",
                "entry": entry,
                "stop": stop,
                "targets": target,
                "confidence": 0.75,
                "reasoning": "Bollinger width > 0.05. Volatility expansion for BUY.",
            }
        return None


class KeltnerVolatilityStrategy(BaseStrategy):
    name = "Keltner Volatility"

    def evaluate(self, market_data):
        ind = normalize_indicator_schema(market_data.get("indicators") or {})
        candles = market_data.get("candles") or []
        if ind.get("keltner_width", 0) > 0.04 and candles:
            levels = _breakout_levels(candles, ind)
            if levels is None:
                return None
            entry, stop, target = levels
            return {
                "direction": "BUY",
                "entry": entry,
                "stop": stop,
                "targets": target,
                "confidence": 0.7,
                "reasoning": "Keltner width > 0.04. Volatility signal for BUY.",
            }
        return None


def volatility_strategies(asset, timeframe, market_data):
    strategies = [ATRBreakoutStrategy(), BBWidthVolatilityStrategy(), KeltnerVolatilityStrategy()]
    signals = []
    for strat in strategies:
        sig = strat.evaluate(market_data)
        if sig:
            sig["asset"] = asset
            sig["symbol"] = asset
            sig["timeframe"] = timeframe
            sig["strategy_name"] = getattr(strat, "name", strat.__class__.__name__)
            sig["strategy_group"] = "volatility"
            sig["strength"] = float(sig.get("confidence", 0) or 0)
            sig["volatility"] = float(market_data.get("indicators", {}).get("bollinger", {}).get("width", 0) or 0)
            signals.append(sig)
    return signals
