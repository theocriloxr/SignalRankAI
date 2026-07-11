from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Any

from services.asset_registry import AssetProfile, build_asset_profile


@dataclass(frozen=True, slots=True)
class MarketIntelligence:
    asset: str
    asset_class: str
    market_open: bool
    trading_allowed: bool
    session: str
    liquidity_score: float
    spread_quality: str
    volatility_regime: str
    trend_regime: str
    news_risk: str
    strategy_compatibility: float
    asset_health_score: float
    scan_priority: float
    reasons: tuple[str, ...] = field(default_factory=tuple)


def _now_utc(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def detect_session(now: datetime | None = None) -> str:
    current = _now_utc(now)
    t = current.time()
    if time(7, 0) <= t < time(12, 0):
        return "London"
    if time(12, 0) <= t < time(16, 0):
        return "London-New York overlap"
    if time(16, 0) <= t < time(21, 0):
        return "New York"
    if time(22, 0) <= t or t < time(7, 0):
        return "Asia"
    return "Transition"


def _market_open(profile: AssetProfile, now: datetime | None = None) -> tuple[bool, str]:
    if profile.asset_class == "crypto":
        return True, "crypto_24_7"
    try:
        from data.market_hours import is_market_session_open

        return bool(is_market_session_open(profile.canonical_symbol)), "market_hours"
    except Exception:
        current = _now_utc(now)
        if current.weekday() >= 5:
            return False, "weekend"
        return True, "fallback_weekday"


def _volatility_regime(signal: dict[str, Any] | None, candles: list[dict[str, Any]] | None) -> tuple[str, float]:
    signal = dict(signal or {})
    try:
        atr_regime = float(signal.get("atr_regime") or signal.get("volatility") or 0.0)
    except Exception:
        atr_regime = 0.0
    if atr_regime:
        if atr_regime >= 3.0:
            return "high", 58.0
        if atr_regime <= 0.7:
            return "low", 62.0
        return "normal", 78.0
    closes = []
    for candle in candles or []:
        try:
            closes.append(float(candle.get("close")))
        except Exception:
            continue
    if len(closes) < 20:
        return "unknown", 55.0
    returns = [abs((closes[i] - closes[i - 1]) / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1]]
    if not returns:
        return "unknown", 55.0
    avg = sum(returns[-20:]) / min(20, len(returns))
    if avg > 0.012:
        return "high", 58.0
    if avg < 0.001:
        return "low", 60.0
    return "normal", 78.0


def _trend_regime(candles: list[dict[str, Any]] | None) -> tuple[str, float]:
    closes = []
    for candle in candles or []:
        try:
            closes.append(float(candle.get("close")))
        except Exception:
            continue
    if len(closes) < 30:
        return "unknown", 55.0
    fast = sum(closes[-10:]) / 10
    slow = sum(closes[-30:]) / 30
    slope = (closes[-1] - closes[-10]) / max(abs(closes[-10]), 1e-9)
    if abs(fast - slow) / max(abs(slow), 1e-9) < 0.0015:
        return "ranging", 62.0
    if fast > slow and slope > 0:
        return "trending_up", 82.0
    if fast < slow and slope < 0:
        return "trending_down", 82.0
    return "transition", 68.0


def _session_liquidity(asset_class: str, session: str) -> float:
    if asset_class == "crypto":
        return 78.0 if session in {"London", "London-New York overlap", "New York"} else 65.0
    if asset_class == "fx":
        return 90.0 if "London" in session or "New York" in session else 60.0
    if asset_class in {"commodity", "index", "stock"}:
        return 88.0 if "New York" in session else 70.0 if "London" in session else 45.0
    return 55.0


def evaluate_market(
    asset: str,
    *,
    signal: dict[str, Any] | None = None,
    candles: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> MarketIntelligence:
    profile = build_asset_profile(asset)
    session = detect_session(now)
    is_open, open_reason = _market_open(profile, now)
    volatility, volatility_score = _volatility_regime(signal, candles)
    trend, trend_score = _trend_regime(candles)
    liquidity = _session_liquidity(profile.asset_class, session)
    news_risk = str((signal or {}).get("news_risk") or "low").lower()
    news_score = 35.0 if news_risk in {"high", "red", "blocked"} else 78.0 if news_risk in {"medium", "yellow"} else 90.0
    strategy_compat = 75.0
    strategy_name = str((signal or {}).get("strategy_name") or "").lower()
    if strategy_name:
        if "scalp" in strategy_name and session in {"London", "London-New York overlap", "New York"}:
            strategy_compat = 86.0
        elif "trend" in strategy_name and trend.startswith("trending"):
            strategy_compat = 88.0
        elif "mean" in strategy_name and trend == "ranging":
            strategy_compat = 84.0
    health = max(0.0, min(100.0, (liquidity * 0.30) + (volatility_score * 0.20) + (trend_score * 0.20) + (news_score * 0.20) + (strategy_compat * 0.10)))
    reasons = [open_reason, f"session={session}", f"volatility={volatility}", f"trend={trend}", f"news={news_risk}"]
    trading_allowed = bool(is_open and health >= 45.0 and news_risk not in {"blocked", "red"})
    priority = health if trading_allowed else min(health, 35.0)
    return MarketIntelligence(
        asset=profile.canonical_symbol,
        asset_class=profile.asset_class,
        market_open=is_open,
        trading_allowed=trading_allowed,
        session=session,
        liquidity_score=round(liquidity, 1),
        spread_quality="excellent" if liquidity >= 85 else "good" if liquidity >= 65 else "thin",
        volatility_regime=volatility,
        trend_regime=trend,
        news_risk=news_risk,
        strategy_compatibility=round(strategy_compat, 1),
        asset_health_score=round(health, 1),
        scan_priority=round(priority, 1),
        reasons=tuple(reasons),
    )


def market_to_signal_fields(market: MarketIntelligence) -> dict[str, Any]:
    return {
        "asset_class": market.asset_class,
        "market_session": market.session,
        "market_open": market.market_open,
        "trading_allowed": market.trading_allowed,
        "liquidity_score": market.liquidity_score,
        "spread_quality": market.spread_quality,
        "volatility_regime": market.volatility_regime,
        "trend_regime": market.trend_regime,
        "news_risk": market.news_risk,
        "asset_health_score": market.asset_health_score,
        "scan_priority": market.scan_priority,
        "market_reasons": list(market.reasons),
    }
