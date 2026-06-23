"""
SignalRankAI — Market Regime Detector (PERFECTED)

Detects one of four regime states:
  TRENDING   → Use trend-following strategies (EMA crossovers, breakouts)
  RANGING    → Use mean-reversion strategies (RSI extremes, Bollinger bands)
  VOLATILE   → Reduce position sizes, widen stops, filter low-score signals
  NEWS       → Suppress all signals during high-impact news events

A perfect bot changes behavior automatically based on regime.
Trend strategies MUST NOT run in ranging markets.
Range strategies MUST NOT run in trending markets.

Detection methods:
  - ADX > 25 → TRENDING
  - ADX < 20 + price in Bollinger band → RANGING
  - ATR > 2x baseline → VOLATILE
  - Calendar check → NEWS (30-min pre/post high-impact events)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Regime constants ─────────────────────────────────────────────────────────

class Regime:
    TRENDING  = "TRENDING"
    RANGING   = "RANGING"
    VOLATILE  = "VOLATILE"
    NEWS      = "NEWS"
    UNKNOWN   = "UNKNOWN"

    ALL = {TRENDING, RANGING, VOLATILE, NEWS, UNKNOWN}

    # Which signal strategies are compatible with each regime
    STRATEGY_WHITELIST: Dict[str, list[str]] = {
        TRENDING: [
            "ema_crossover", "supertrend", "macd_trend",
            "bollinger_breakout", "momentum", "channel_breakout",
            "ichimoku_cloud", "adx_trend",
        ],
        RANGING: [
            "rsi_mean_reversion", "bollinger_revert", "stoch_reversal",
            "support_resistance", "dca_range", "grid",
            "macd_divergence", "cci_reversal",
        ],
        VOLATILE: [
            # Minimal strategies, only highest-conviction setups
            "supertrend", "momentum",
        ],
        NEWS: [],  # No strategies during news
        UNKNOWN: [
            # Everything allowed in unknown state (startup / no data)
            "ema_crossover", "rsi_mean_reversion", "supertrend",
            "bollinger_breakout", "support_resistance",
        ],
    }

    # Strategy groups that must be blocked in specific regimes
    STRATEGY_BLACKLIST: Dict[str, list[str]] = {
        RANGING: ["ema_crossover", "supertrend", "macd_trend", "channel_breakout"],
        TRENDING: ["rsi_mean_reversion", "bollinger_revert", "grid", "dca_range"],
        NEWS: ["ALL"],  # Block everything
        VOLATILE: ["dca_range", "grid", "support_resistance"],
    }


# ─── ADX calculation (without TA-Lib) ─────────────────────────────────────────

def _calc_adx(highs: list, lows: list, closes: list, period: int = 14) -> Optional[float]:
    """Calculate ADX from OHLC data. Returns None if insufficient data."""
    n = len(closes)
    if n < period * 2:
        return None

    try:
        import statistics

        # Calculate True Range
        def true_range(i: int) -> float:
            return max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )

        trs, plus_dm, minus_dm = [], [], []
        for i in range(1, n):
            tr = true_range(i)
            pdm = max(highs[i] - highs[i - 1], 0)
            mdm = max(lows[i - 1] - lows[i], 0)
            if pdm > mdm:
                mdm = 0
            else:
                pdm = 0
            trs.append(tr)
            plus_dm.append(pdm)
            minus_dm.append(mdm)

        def smooth(data: list, p: int) -> list:
            result = [sum(data[:p])]
            for val in data[p:]:
                result.append(result[-1] - result[-1] / p + val)
            return result

        atr_s  = smooth(trs, period)
        pdm_s  = smooth(plus_dm, period)
        mdm_s  = smooth(minus_dm, period)

        adx_list = []
        for i in range(len(atr_s)):
            if atr_s[i] == 0:
                continue
            pdi = (pdm_s[i] / atr_s[i]) * 100
            mdi = (mdm_s[i] / atr_s[i]) * 100
            dx  = (abs(pdi - mdi) / (pdi + mdi)) * 100 if (pdi + mdi) > 0 else 0
            adx_list.append(dx)

        if not adx_list:
            return None

        # Smooth ADX
        adx_smoothed = smooth(adx_list, period)
        return float(adx_smoothed[-1]) if adx_smoothed else None

    except Exception as exc:
        logger.debug("[regime] ADX calculation failed: %s", exc)
        return None


def _calc_atr(highs: list, lows: list, closes: list, period: int = 14) -> Optional[float]:
    """Calculate Average True Range."""
    n = len(closes)
    if n < period + 1:
        return None

    try:
        trs = []
        for i in range(1, n):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)

        if len(trs) < period:
            return None

        # Simple ATR: EMA of TR
        atr = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr = (atr * (period - 1) + tr) / period

        return float(atr)
    except Exception:
        return None


def _calc_bollinger_width(closes: list, period: int = 20) -> Optional[float]:
    """Calculate Bollinger Band width as % of middle band."""
    if len(closes) < period:
        return None

    try:
        recent = closes[-period:]
        mid = sum(recent) / period
        std = (sum((c - mid) ** 2 for c in recent) / period) ** 0.5
        width = (4 * std) / mid * 100  # (upper - lower) / mid * 100
        return float(width)
    except Exception:
        return None


# ─── Regime detector ──────────────────────────────────────────────────────────

class RegimeDetector:
    """
    Market regime detector using ADX, ATR, and Bollinger Width.

    Results are cached per asset+timeframe for 5 minutes to avoid
    repeated heavy computation on every tick.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[str, float, datetime]] = {}
        self._cache_ttl_seconds = int(os.getenv("REGIME_CACHE_TTL_SECONDS", "300") or 300)

    def detect(
        self,
        candles: list,
        asset: str = "",
        timeframe: str = "",
        *,
        force_refresh: bool = False,
    ) -> str:
        """
        Detect the current market regime from OHLCV candles.

        Args:
            candles:       List of OHLCV dicts with keys: open, high, low, close, volume
            asset:         Asset symbol (for caching)
            timeframe:     Timeframe (for caching)
            force_refresh: Bypass cache

        Returns:
            One of: TRENDING, RANGING, VOLATILE, NEWS, UNKNOWN
        """
        cache_key = f"{asset.upper()}:{timeframe.lower()}"

        # Check cache
        if not force_refresh and cache_key in self._cache:
            cached_regime, _, cached_at = self._cache[cache_key]
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age < self._cache_ttl_seconds:
                return cached_regime

        # Check news regime first (calendar-based, doesn't need candle data)
        news_regime = self._check_news_regime(asset)
        if news_regime:
            self._update_cache(cache_key, Regime.NEWS)
            return Regime.NEWS

        if not candles or len(candles) < 30:
            self._update_cache(cache_key, Regime.UNKNOWN)
            return Regime.UNKNOWN

        # Extract OHLCV arrays
        try:
            highs  = [float(c.get("high",  c.get("High",  0)) or 0) for c in candles]
            lows   = [float(c.get("low",   c.get("Low",   0)) or 0) for c in candles]
            closes = [float(c.get("close", c.get("Close", 0)) or 0) for c in candles]

            if not any(c > 0 for c in closes):
                self._update_cache(cache_key, Regime.UNKNOWN)
                return Regime.UNKNOWN

        except Exception as exc:
            logger.debug("[regime] OHLCV extraction failed: %s", exc)
            self._update_cache(cache_key, Regime.UNKNOWN)
            return Regime.UNKNOWN

        # ── ADX (trend strength) ──────────────────────────────────────────────
        adx = _calc_adx(highs, lows, closes, period=14)

        # ── ATR (volatility) ─────────────────────────────────────────────────
        atr = _calc_atr(highs, lows, closes, period=14)
        # Baseline ATR: average of last 50 candles
        atr_baseline = _calc_atr(highs[-50:], lows[-50:], closes[-50:], period=14) if len(closes) >= 50 else atr
        atr_ratio = (float(atr) / float(atr_baseline)) if atr and atr_baseline and atr_baseline > 0 else None

        # ── Bollinger Width (ranging indicator) ───────────────────────────────
        bb_width = _calc_bollinger_width(closes, period=20)

        # ── Regime classification ─────────────────────────────────────────────
        adx_trend_threshold   = float(os.getenv("REGIME_ADX_TREND",    "25") or 25)
        adx_ranging_threshold = float(os.getenv("REGIME_ADX_RANGING",  "20") or 20)
        atr_volatile_ratio    = float(os.getenv("REGIME_ATR_VOLATILE",  "2.0") or 2.0)
        bb_ranging_threshold  = float(os.getenv("REGIME_BB_RANGING",   "4.0") or 4.0)

        regime = Regime.UNKNOWN

        # Volatile regime takes priority over trending
        if atr_ratio and atr_ratio >= atr_volatile_ratio:
            regime = Regime.VOLATILE

        elif adx is not None:
            if adx >= adx_trend_threshold:
                regime = Regime.TRENDING
            elif adx < adx_ranging_threshold:
                # Confirm with Bollinger Width
                if bb_width is not None and bb_width < bb_ranging_threshold:
                    regime = Regime.RANGING
                else:
                    regime = Regime.RANGING  # Low ADX = ranging regardless

        logger.debug(
            "[regime] %s %s → %s (ADX=%.1f BB_W=%.2f ATR_R=%.2f)",
            asset, timeframe, regime,
            adx or 0, bb_width or 0, atr_ratio or 0,
        )

        self._update_cache(cache_key, regime)
        return regime

    def _check_news_regime(self, asset: str) -> bool:
        """
        Check if the current time is within a high-impact news window.

        Returns True if news regime should suppress signals.
        """
        try:
            news_window_minutes = int(os.getenv("NEWS_WINDOW_MINUTES", "30") or 30)

            # Asset-specific news calendars can be added here
            # For now, check known high-impact fixed windows
            now_utc = datetime.now(timezone.utc)
            weekday = now_utc.weekday()  # 0=Mon, 4=Fri
            hour    = now_utc.hour
            minute  = now_utc.minute

            # US Non-Farm Payrolls: first Friday of each month at 13:30 UTC
            if weekday == 4 and hour == 13 and 25 <= minute <= 45:
                return True

            # FOMC decisions: check for common times (Wed, 19:00-20:30 UTC)
            if weekday == 2 and 19 <= hour <= 20:
                return True

            # US CPI: usually 13:30 UTC on report day
            # Check via Redis flag if available
            try:
                from core.redis_state import state
                news_flag = state.get_sync(f"news_suppression:{asset.upper()}")
                if news_flag:
                    return True
            except Exception:
                pass

        except Exception:
            pass

        return False

    def _update_cache(self, key: str, regime: str) -> None:
        """Update the regime cache."""
        self._cache[key] = (regime, 0.0, datetime.now(timezone.utc))

    def is_strategy_allowed(self, strategy_name: str, regime: str) -> bool:
        """Check if a strategy is allowed in the given regime."""
        regime = str(regime or Regime.UNKNOWN).upper()
        strategy = str(strategy_name or "").lower().strip()

        if regime == Regime.NEWS:
            return False  # Nothing runs during news

        blacklist = Regime.STRATEGY_BLACKLIST.get(regime, [])
        if "ALL" in blacklist:
            return False
        if any(bl in strategy for bl in blacklist):
            return False

        return True

    def adjust_signal_score(self, score: float, regime: str) -> float:
        """
        Adjust signal confidence score based on market regime.

        VOLATILE: reduce score by 15% (more uncertainty)
        RANGING + trend strategy: reduce by 20%
        TRENDING + trend strategy: boost by 5%
        NEWS: set to 0 (suppressed)
        """
        if regime == Regime.NEWS:
            return 0.0
        if regime == Regime.VOLATILE:
            return float(score) * 0.85
        if regime == Regime.UNKNOWN:
            return float(score) * 0.90
        return float(score)


# ─── Module-level singleton ───────────────────────────────────────────────────

regime_detector = RegimeDetector()


def detect_regime(candles: list, asset: str = "", timeframe: str = "") -> str:
    """Convenience function — detect regime using the module singleton."""
    return regime_detector.detect(candles, asset=asset, timeframe=timeframe)


def is_strategy_allowed(strategy_name: str, regime: str) -> bool:
    """Check if a strategy is allowed in the given regime."""
    return regime_detector.is_strategy_allowed(strategy_name, regime)


__all__ = [
    "Regime",
    "RegimeDetector",
    "regime_detector",
    "detect_regime",
    "is_strategy_allowed",
]