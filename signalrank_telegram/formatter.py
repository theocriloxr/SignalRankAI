"""
SignalRankAI — Signal Formatter (PERFECTED)

Implements the "Every Signal Must Be Explainable" specification.

Every signal answers:
  • Why generated?
  • Why now?
  • What invalidates it?
  • What confirms it?

Tier-gated output:
  FREE    → Asset + direction + timeframe + teaser (no exact levels)
  PREMIUM → Full signal: entry, SL, TP1+TP2, score breakdown, strategy
  VIP     → Full signal + TP3 + regime + Gemini insight + institutional concepts

Signal format example (VIP):
  👑 VIP SIGNAL — XAUUSD LONG [4h]
  ─────────────────────────────────
  Score: 94/100 | Regime: TRENDING

  Entry Zone:   1,923.50
  Stop Loss:    1,916.80
  TP1:          1,934.20 (+0.56%) → 0.83R
  TP2:          1,948.00 (+1.27%) → 1.89R
  TP3:          1,961.50 (+1.97%) → 2.94R ← VIP ONLY

  📊 Signal Breakdown:
  Trend Score:    87
  Volume Score:   91
  Liquidity Score: 83
  ML Score:       95

  🧠 Reason:
  Bullish market structure shift, liquidity sweep completed,
  volume expansion confirmed. Smart money accumulation zone.

  ⚠️ Invalidated if: Price closes below 1,916.80
  ✅ Confirmed by: Volume > 20D MA on next candle
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# ─── Formatting helpers ───────────────────────────────────────────────────────

def _fmt_price(value, asset: str = "") -> str:
    """Format a price value with appropriate decimal places for the asset."""
    try:
        v = float(value)
        if v <= 0:
            return "N/A"

        asset_u = str(asset or "").upper()

        # Forex majors: 5 decimal places
        if any(asset_u.endswith(pair) for pair in ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD")):
            if "JPY" in asset_u:
                return f"{v:.3f}"
            if v > 100:
                return f"{v:,.3f}"
            return f"{v:.5f}"

        # Crypto: adapt based on magnitude
        if v >= 10000:
            return f"{v:,.2f}"
        elif v >= 100:
            return f"{v:,.3f}"
        elif v >= 1:
            return f"{v:.4f}"
        else:
            return f"{v:.6f}"
    except Exception:
        return str(value) if value else "N/A"


def _parse_tp_levels(raw) -> List[float]:
    """Parse take-profit levels from any format into a list of floats."""
    if raw is None:
        return []
    if isinstance(raw, (int, float)):
        return [float(raw)] if raw > 0 else []
    if isinstance(raw, (list, tuple)):
        result = []
        for item in raw:
            try:
                v = float(item.get("price") if isinstance(item, dict) else item)
                if v > 0:
                    result.append(v)
            except Exception:
                continue
        return result
    if isinstance(raw, str):
        try:
            return _parse_tp_levels(json.loads(raw))
        except Exception:
            try:
                return [float(raw)]
            except Exception:
                return []
    return []


def _calc_pct(entry: float, target: float, direction: str) -> Optional[float]:
    """Calculate percentage gain/loss from entry to target."""
    try:
        if entry <= 0:
            return None
        if direction == "long":
            return ((target - entry) / entry) * 100
        else:
            return ((entry - target) / entry) * 100
    except Exception:
        return None


def _calc_r(entry: float, stop: float, target: float, direction: str) -> Optional[float]:
    """Calculate R-multiple for a target."""
    try:
        risk = abs(entry - stop)
        if risk <= 0:
            return None
        if direction == "long":
            reward = target - entry
        else:
            reward = entry - target
        return reward / risk
    except Exception:
        return None


def _score_bar(score: float, width: int = 10) -> str:
    """Create a visual score bar."""
    filled = round((score / 100) * width)
    return "█" * filled + "░" * (width - filled)


def _direction_emoji(direction: str) -> str:
    d = str(direction or "").lower()
    if d in ("long", "buy"):
        return "📈"
    if d in ("short", "sell"):
        return "📉"
    return "↔️"


def _regime_emoji(regime: str) -> str:
    r = str(regime or "").upper()
    mapping = {
        "TRENDING":   "🚀",
        "RANGING":    "🔄",
        "VOLATILE":   "⚡",
        "BREAKOUT":   "💥",
        "REVERSAL":   "🔁",
        "BEARISH":    "🐻",
        "BULLISH":    "🐂",
        "NEUTRAL":    "⚖️",
    }
    for key, emoji in mapping.items():
        if key in r:
            return emoji
    return "📊"


# ─── Tier-gated formatters ────────────────────────────────────────────────────

def _format_free(signal: dict) -> str:
    """FREE tier format: teaser only, drives upgrade CTA."""
    asset       = str(signal.get("asset") or signal.get("symbol") or "?").upper()
    timeframe   = str(signal.get("timeframe") or "?").upper()
    direction   = str(signal.get("direction") or "long").lower()
    score       = signal.get("score")
    signal_id   = str(signal.get("signal_id") or "").upper()[:8]
    regime      = str(signal.get("regime") or "")

    dir_emoji   = _direction_emoji(direction)
    dir_label   = direction.upper()
    score_str   = f"{float(score):.0f}" if score is not None else "—"
    regime_hint = f" • {regime.title()}" if regime and regime.upper() not in ("UNKNOWN", "NEUTRAL") else ""

    lines = [
        f"📊 <b>SignalRankAI Signal Alert</b>",
        "",
        f"{dir_emoji} <b>{asset}</b> {dir_label} [{timeframe}]{regime_hint}",
        f"Score: <b>{score_str}/100</b>",
        "",
        "🔒 <b>Exact entry, stop loss & targets available on Premium/VIP.</b>",
        "",
        "Upgrade now to access:",
        "• Precise entry zone",
        "• Stop loss level",
        "• Multiple take-profit targets",
        "• Live trade monitoring",
        "• MT5 auto-execution",
        "",
        f"→ /upgrade to unlock this signal",
        f"<i>Ref: {signal_id}</i>",
    ]
    return "\n".join(lines)


def _format_premium(signal: dict) -> str:
    """PREMIUM tier format: full signal, entry/SL/TP1+TP2, score breakdown."""
    asset       = str(signal.get("asset") or signal.get("symbol") or "?").upper()
    timeframe   = str(signal.get("timeframe") or "?").upper()
    direction   = str(signal.get("direction") or "long").lower()
    entry       = signal.get("entry") or signal.get("close_price")
    stop_loss   = signal.get("stop_loss") or signal.get("stop")
    take_profit = signal.get("take_profit") or signal.get("tp_levels") or signal.get("targets")
    score       = signal.get("score")
    strategy    = str(signal.get("strategy_name") or signal.get("strategy") or "")
    signal_id   = str(signal.get("signal_id") or "").upper()[:8]
    ml_prob     = signal.get("ml_probability")
    regime      = str(signal.get("regime") or "")
    rr_ratio    = signal.get("rr_ratio") or signal.get("rr_estimate") or signal.get("risk_reward")

    # Sub-scores
    trend_score = signal.get("trend_score") or signal.get("trend_conf")
    volume_score = signal.get("volume_score")
    ml_score = signal.get("ml_score") or (ml_prob and ml_prob * 100)

    tp_levels = _parse_tp_levels(take_profit)
    dir_emoji  = _direction_emoji(direction)
    dir_label  = direction.upper()

    # Entry / SL formatting
    entry_f  = float(entry) if entry else None
    sl_f     = float(stop_loss) if stop_loss else None
    score_f  = float(score) if score is not None else None
    rr_f     = float(rr_ratio) if rr_ratio else None

    lines = [
        f"⭐ <b>PREMIUM SIGNAL — {asset} {dir_label}</b>",
        f"Timeframe: <b>[{timeframe}]</b>",
    ]

    if regime:
        lines.append(f"Regime: <b>{_regime_emoji(regime)} {regime.title()}</b>")

    if score_f is not None:
        bar = _score_bar(score_f)
        lines.append(f"Score: <b>{score_f:.0f}/100</b> {bar}")

    lines.append("")

    # Prices
    lines.append(f"{'─' * 32}")
    if entry_f:
        lines.append(f"🎯 Entry Zone:  <b>{_fmt_price(entry_f, asset)}</b>")
    if sl_f:
        lines.append(f"🛑 Stop Loss:   <b>{_fmt_price(sl_f, asset)}</b>")

    # TP levels (Premium gets TP1 + TP2, not TP3)
    tp_labels = ["🎯 TP1:", "💛 TP2:"]
    for i, (tp, label) in enumerate(zip(tp_levels[:2], tp_labels)):
        tp_f = float(tp)
        pct  = _calc_pct(entry_f, tp_f, direction) if entry_f else None
        r    = _calc_r(entry_f, sl_f, tp_f, direction) if entry_f and sl_f else None
        pct_str = f" (+{pct:.2f}%)" if pct is not None and pct >= 0 else ""
        r_str   = f" → {r:.2f}R" if r is not None else ""
        lines.append(f"{label}         <b>{_fmt_price(tp_f, asset)}</b>{pct_str}{r_str}")

    if len(tp_levels) > 2:
        lines.append("🔒 TP3:         <i>VIP only — /upgrade</i>")

    lines.append(f"{'─' * 32}")

    # Score breakdown
    if any(v is not None for v in [trend_score, volume_score, ml_score]):
        lines.append("\n📊 <b>Signal Breakdown:</b>")
        if trend_score is not None:
            lines.append(f"  Trend Score:   {float(trend_score):.0f}")
        if volume_score is not None:
            lines.append(f"  Volume Score:  {float(volume_score):.0f}")
        if ml_score is not None:
            lines.append(f"  ML Score:      {float(ml_score):.0f}")

    # Strategy
    if strategy:
        lines.append(f"\n📐 Strategy: <b>{strategy}</b>")

    # Invalidation
    if sl_f:
        lines.append(f"\n⚠️ <i>Invalidated if: Price closes below {_fmt_price(sl_f, asset)}</i>")

    lines += [
        "",
        f"<i>Ref: {signal_id}</i>",
    ]

    return "\n".join(lines)


def _format_vip(signal: dict) -> str:
    """VIP tier format: full signal + TP3 + regime + explainability + institutional concepts."""
    asset         = str(signal.get("asset") or signal.get("symbol") or "?").upper()
    timeframe     = str(signal.get("timeframe") or "?").upper()
    direction     = str(signal.get("direction") or "long").lower()
    entry         = signal.get("entry") or signal.get("close_price")
    stop_loss     = signal.get("stop_loss") or signal.get("stop")
    take_profit   = signal.get("take_profit") or signal.get("tp_levels") or signal.get("targets")
    score         = signal.get("score")
    strategy      = str(signal.get("strategy_name") or signal.get("strategy") or "")
    signal_id     = str(signal.get("signal_id") or "").upper()[:8]
    ml_prob       = signal.get("ml_probability")
    regime        = str(signal.get("regime") or "")
    htf_bias      = str(signal.get("htf_bias") or "")
    confluence    = signal.get("confluence")
    trade_logic   = str(signal.get("trade_logic") or "")
    invalidation  = str(signal.get("invalidation") or "")
    session       = str(signal.get("session") or "")
    news_score    = signal.get("news_score") or signal.get("news_sentiment")
    
    # Sub-scores
    trend_score    = signal.get("trend_score") or signal.get("trend_conf")
    volume_score   = signal.get("volume_score")
    liquidity_score = signal.get("liquidity_score")
    ml_score       = signal.get("ml_score") or (ml_prob and ml_prob * 100)
    sentiment_score = signal.get("sentiment_score") or news_score

    # Institutional concept tags
    inst_concepts = []
    if signal.get("has_order_block"):       inst_concepts.append("Order Block")
    if signal.get("has_fvg"):               inst_concepts.append("FVG")
    if signal.get("has_liquidity_sweep"):   inst_concepts.append("Liq. Sweep")
    if signal.get("has_bos"):               inst_concepts.append("BOS")
    if signal.get("has_choch"):             inst_concepts.append("CHoCH")
    if signal.get("has_breaker"):           inst_concepts.append("Breaker Block")
    if signal.get("premium_discount"):      inst_concepts.append("Premium/Discount")

    tp_levels = _parse_tp_levels(take_profit)
    dir_emoji  = _direction_emoji(direction)
    dir_label  = direction.upper()

    entry_f = float(entry) if entry else None
    sl_f    = float(stop_loss) if stop_loss else None
    score_f = float(score) if score is not None else None

    regime_emoji = _regime_emoji(regime)

    lines = [
        f"👑 <b>VIP SIGNAL — {asset} {dir_label}</b>",
        f"Timeframe: <b>[{timeframe}]</b>",
    ]

    # Regime + session row
    regime_str = f"{regime_emoji} {regime.title()}" if regime else ""
    session_str = f"• {session}" if session else ""
    if regime_str or session_str:
        lines.append(f"Regime: <b>{regime_str} {session_str}</b>".strip())

    if score_f is not None:
        bar = _score_bar(score_f)
        lines.append(f"Score: <b>{score_f:.0f}/100</b> {bar}")

    if htf_bias:
        lines.append(f"HTF Bias: <b>{htf_bias}</b>")

    lines.append(f"\n{'═' * 32}")

    # Prices
    if entry_f:
        lines.append(f"🎯 Entry Zone:  <b>{_fmt_price(entry_f, asset)}</b>")
    if sl_f:
        lines.append(f"🛑 Stop Loss:   <b>{_fmt_price(sl_f, asset)}</b>")

    # All TP levels
    tp_emojis = ["🎯", "💛", "✅"]
    tp_labels = ["TP1:", "TP2:", "TP3:"]
    for i, tp in enumerate(tp_levels[:3]):
        tp_f   = float(tp)
        pct    = _calc_pct(entry_f, tp_f, direction) if entry_f else None
        r      = _calc_r(entry_f, sl_f, tp_f, direction) if entry_f and sl_f else None
        pct_str = f" (+{pct:.2f}%)" if pct is not None and pct >= 0 else ""
        r_str   = f" → <b>{r:.2f}R</b>" if r is not None else ""
        emoji   = tp_emojis[i] if i < len(tp_emojis) else "🎯"
        label   = tp_labels[i] if i < len(tp_labels) else f"TP{i+1}:"
        lines.append(f"{emoji} {label}        <b>{_fmt_price(tp_f, asset)}</b>{pct_str}{r_str}")

    lines.append(f"{'═' * 32}\n")

    # Score breakdown
    sub_scores = []
    if trend_score is not None:    sub_scores.append(("Trend Score",    float(trend_score)))
    if volume_score is not None:   sub_scores.append(("Volume Score",   float(volume_score)))
    if liquidity_score is not None: sub_scores.append(("Liquidity Score", float(liquidity_score)))
    if ml_score is not None:       sub_scores.append(("ML Score",       float(ml_score)))
    if sentiment_score is not None: sub_scores.append(("Sentiment",     float(sentiment_score)))

    if sub_scores:
        lines.append("📊 <b>Signal Breakdown:</b>")
        for label, val in sub_scores:
            bar = _score_bar(val, width=8)
            lines.append(f"  {label:<18} <b>{val:.0f}</b> {bar}")
        lines.append("")

    # Institutional concepts
    if inst_concepts:
        lines.append(f"🏛️ <b>Concepts:</b> {' • '.join(inst_concepts)}")
        lines.append("")

    # Trade logic / reason
    if trade_logic:
        lines.append("🧠 <b>Why This Trade:</b>")
        lines.append(f"<i>{trade_logic}</i>")
        lines.append("")
    elif confluence and isinstance(confluence, dict):
        reasons = []
        if confluence.get("trend_aligned"):  reasons.append("trend aligned")
        if confluence.get("volume_spike"):    reasons.append("volume expansion confirmed")
        if confluence.get("liquidity_swept"): reasons.append("liquidity sweep completed")
        if confluence.get("structure_break"): reasons.append("market structure shift")
        if reasons:
            lines.append("🧠 <b>Reason:</b>")
            lines.append(f"<i>{', '.join(r.capitalize() for r in reasons)}.</i>")
            lines.append("")

    # Invalidation
    inv_text = invalidation or (f"Price closes below {_fmt_price(sl_f, asset)}" if sl_f else "")
    if inv_text:
        lines.append(f"⚠️ <b>Invalidated if:</b> {inv_text}")

    # Strategy
    if strategy:
        lines.append(f"📐 <b>Strategy:</b> {strategy}")

    lines += [
        "",
        f"<i>Ref: {signal_id}</i>",
    ]

    return "\n".join(lines)


# ─── Main formatter entry point ───────────────────────────────────────────────

def format_signal(
    signal: dict,
    user_tier: Optional[str] = None,
    display_tier: Optional[str] = None,
) -> str:
    """
    Format a signal dictionary for delivery to a user.

    Args:
        signal:       Signal data dictionary
        user_tier:    The user's actual subscription tier
        display_tier: The tier to use for formatting (may differ from user_tier
                      if e.g. owner/admin should see VIP format)

    Returns:
        HTML-formatted signal message string
    """
    if not signal:
        return ""

    # Resolve effective display tier
    effective_tier = str(display_tier or user_tier or "free").strip().lower()
    if effective_tier in ("owner", "admin"):
        effective_tier = "vip"

    try:
        if effective_tier == "vip":
            return _format_vip(signal)
        elif effective_tier == "premium":
            return _format_premium(signal)
        else:
            return _format_free(signal)
    except Exception as exc:
        logger.warning("[formatter] format_signal failed for tier=%s: %s", effective_tier, exc)
        # Fallback: always show at least the asset/direction
        try:
            asset     = str(signal.get("asset") or "?").upper()
            direction = str(signal.get("direction") or "?").upper()
            timeframe = str(signal.get("timeframe") or "?")
            return f"📊 <b>Signal: {asset} {direction} [{timeframe}]</b>\n<i>(Formatting error — contact support)</i>"
        except Exception:
            return "📊 Signal update available."


__all__ = [
    "format_signal",
    "_format_free",
    "_format_premium",
    "_format_vip",
    "_parse_tp_levels",
    "_fmt_price",
]