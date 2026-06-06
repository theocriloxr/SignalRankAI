"""
Tier-Gated Signal Formatter - Hides the Alpha for FREE Users

This module implements the Conversion Funnel logic:
- FREE users see: Asset, Direction, Entry, TP1 (visible)
- FREE users DON'T see: TP2, TP3, Stop Loss, AI Confidence (locked with 🔒)
- PREMIUM/VIP users see: Everything

Usage:
    from signalrank_telegram.tier_gated_formatter import format_tiered_signal
    
    # For FREE user
    text, markup = format_tiered_signal(signal, "free")
    
    # For PREMIUM user  
    text, markup = format_tiered_signal(signal, "premium")
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.tier_constants import TIER_SCORE_THRESHOLDS
from engine.signal_metrics import (
    resolve_confidence_ratio,
    resolve_confluence_percent,
    resolve_ml_probability,
    resolve_score_percent,
)

logger = logging.getLogger(__name__)


def _parse_tp_levels(tp_raw: Any) -> List[float]:
    """Parse take_profit field into list of TP prices."""
    import json
    if tp_raw is None:
        return []
    if isinstance(tp_raw, (int, float)):
        return [float(tp_raw)]
    if isinstance(tp_raw, list):
        out: List[float] = []
        for x in tp_raw:
            try:
                if isinstance(x, dict):
                    v = x.get("price") or x.get("tp") or x.get("target")
                    if v is not None:
                        out.append(float(v))
                elif x is not None:
                    out.append(float(x))
            except Exception:
                pass
        return [v for v in out if v > 0]
    try:
        s = str(tp_raw).strip()
        if s.startswith("["):
            data = json.loads(s)
            if isinstance(data, list):
                return [float(x) for x in data if x is not None]
        return [float(s)]
    except Exception:
        pass
    return []


def _fmt_price_clean(price: Any, asset: str = "") -> str:
    """Format a price value cleanly."""
    try:
        p = float(price)
    except Exception:
        return str(price)
    asset_up = str(asset).upper()
    # BTC/ETH — 2 dp
    if any(c in asset_up for c in ("BTC", "ETH")):
        return f"{p:,.2f}"
    # JPY crosses — 3 dp
    if "JPY" in asset_up:
        return f"{p:.3f}"
    # Large prices (Gold >= 1000, stocks) — 2 dp
    if p >= 1_000:
        return f"{p:,.2f}"
    # FX/alts — 5 dp if < 10, else 4 dp
    if p < 10:
        return f"{p:.5f}"
    return f"{p:.4f}"


def format_tiered_signal(signal: Dict[str, Any], user_tier: str) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """
    Format signal with tier-gated content hiding the Alpha.
    
    Args:
        signal: Signal dict with all fields
        user_tier: User's tier (free, premium, vip, admin, owner)
    
    Returns:
        tuple: (message_text, reply_markup)
    """
    tier = str(user_tier).strip().lower()
    is_free = tier == "free"
    is_premium = tier in ["premium", "vip", "owner", "admin"]
    
    # Asset emoji
    asset = signal.get("asset", "UNKNOWN")
    emoji = "🪙" if any(c in asset.upper() for c in ("BTC", "ETH", "USDT", "BNB")) else "📈"
    
    # Direction
    direction = signal.get("direction", "long")
    direction_str = "🟢 LONG" if str(direction).lower() in ("long", "buy") else "🔴 SHORT"
    
    # Parse TP levels
    tp_levels = _parse_tp_levels(signal.get("take_profit") or signal.get("tp_levels"))
    
    # Score
    score_val = resolve_score_percent(signal)
    if score_val is None:
        conf_ratio = resolve_confidence_ratio(signal)
        score_val = conf_ratio * 100.0 if conf_ratio is not None else 0.0
    
    ml_prob = resolve_ml_probability(signal)
    entry_price = signal.get("entry", "N/A")
    stop_loss_price = signal.get("stop_loss", "N/A")
    
    # Build message
    lines = [
        f"{emoji} **SIGNALRANK ALERT** {emoji}",
        "————————————————————",
        f"🔹 **Asset:** `{asset}`",
        f"🔹 **Action:** **{direction_str}**",
        f"🔹 **Entry:** `{entry_price}`",
        "————————————————————",
    ]
    
    if is_free:
        # FREE: Lock TP2, TP3, SL, ML Confidence
        tp1 = _fmt_price_clean(tp_levels[0], asset) if tp_levels else "N/A"
        lines.extend([
            f"🎯 **TP1:** `{tp1}`",
            "🎯 **TP2 & TP3:** 🔒 `[PREMIUM ONLY]`",
            "🛑 **Stop Loss:** 🔒 `[PREMIUM ONLY]`",
            "🧠 **AI Confidence:** 🔒 `[PREMIUM ONLY]`",
            "————————————————————",
            "⚠️ *Trade at your own risk without Stop Loss data. Upgrade to unlock full risk metrics.*",
        ])
    else:
        # PREMIUM/VIP: Full details
        tp1 = _fmt_price_clean(tp_levels[0], asset) if len(tp_levels) > 0 else "N/A"
        tp2 = _fmt_price_clean(tp_levels[1], asset) if len(tp_levels) > 1 else "N/A"
        tp3 = _fmt_price_clean(tp_levels[2], asset) if len(tp_levels) > 2 else "N/A"
        
        lines.extend([
            "🎯 **Targets:**",
            f"   • TP1: `{tp1}`",
            f"   • TP2: `{tp2}`",
            f"   • TP3: `{tp3}`",
            f"🛑 **Stop Loss:** `{stop_loss_price}`",
        ])
        
        if ml_prob is not None:
            lines.append(f"🧠 **AI Confidence:** `{ml_prob * 100:.1f}%`")
        else:
            lines.append(f"🧠 **AI Confidence:** `{score_val:.1f}%`")
    
    # Build keyboard
    keyboard = []
    signal_id = signal.get("signal_id", "")
    
    if is_premium:
        keyboard.append([
            InlineKeyboardButton("📱 Auto-Execute on MT5", callback_data=f"exec_mt5_{signal_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("⭐ Upgrade to Auto-Execute & Unlock SL", callback_data="upgrade_menu")
        ])
    
    tv_url = f"https://www.tradingview.com/symbols/{asset.replace('USDT', '')}"
    keyboard.append([
        InlineKeyboardButton("📊 TradingView", url=tv_url)
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "\n".join(lines)
    
    return message_text, reply_markup


# ---------------------------------------------------------------------------
# Upgrade 3: Score Gate Filter (Quality Control)
# ---------------------------------------------------------------------------

def should_user_receive_signal(signal_score: float, user_tier: str) -> bool:
    """
    Filter signals based on user's tier quality requirements.
    
    FREE users: Only get signals with score >= 80 (high quality)
    PREMIUM/VIP: Get all signals that pass base engine gates
    
    Args:
        signal_score: ML Score / Consensus Score (0-100)
        user_tier: User's tier
    
    Returns:
        True if user should receive this signal
    """
    tier = str(user_tier).strip().lower()
    
    # FREE tier: minimum 80 score required
    if tier == "free":
        FREE_MIN_SCORE = 80.0
        return signal_score >= FREE_MIN_SCORE
    
    # VIP, PREMIUM, ADMIN, OWNER get everything
    if tier in ["vip", "premium", "owner", "admin"]:
        return True
    
    # Default: allow for valid tiers, block unknown
    return False


def get_paywall_upsell_message() -> str:
    """Get the paywall upsell message for FREE users who hit daily limit."""
    return (
        "🛑 <b>Daily Limit Reached</b>\n\n"
        "You've received your 3 free signals for today.\n\n"
        "<b>Why upgrade to Premium?</b>\n"
        "✅ Unlimited signals - never miss a setup\n"
        "✅ Full Stop Loss data - trade safely\n"
        "✅ TP2 & TP3 targets - maximize profits\n"
        "✅ MT5 Auto-Execute - instant execution\n"
        "✅ AI Confidence scores - know the probability\n\n"
        "<i>Upgrade now: /premium</i>"
    )


# ---------------------------------------------------------------------------
# Quick helper for testing
# ---------------------------------------------------------------------------

def demo_format():
    """Demo the tier-gated formatting."""
    test_signal = {
        "asset": "BTCUSDT",
        "direction": "long",
        "entry": "45000.00",
        "stop_loss": "44500.00",
        "take_profit": ["45500", "46000", "47000"],
        "ml_probability": 0.82,
        "score": 85.0,
        "signal_id": "test-123",
    }
    
    print("=" * 50)
    print("FREE USER:")
    print("=" * 50)
    text, markup = format_tiered_signal(test_signal, "free")
    print(text)
    print()
    
    print("=" * 50)
    print("PREMIUM USER:")
    print("=" * 50)
    text, markup = format_tiered_signal(test_signal, "premium")
    print(text)
    print()
    
    print("=" * 50)
    print("SCORE GATES:")
    print("=" * 50)
    print(f"FREE user receives 85 score? {should_user_receive_signal(85.0, 'free')}")
    print(f"FREE user receives 75 score? {should_user_receive_signal(75.0, 'free')}")
    print(f"PREMIUM user receives 75 score? {should_user_receive_signal(75.0, 'premium')}")


if __name__ == "__main__":
    demo_format()
