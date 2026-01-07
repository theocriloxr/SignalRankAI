"""Tier-specific signal formatting with partial TP display.

Premium: TP1, TP2 with confidence and validity
VIP/Admin/Owner: TP1, TP2, TP3 with confluence, HTF bias, trade logic, invalidation
"""

import os
import json
from typing import Any, Dict as DictType, List, Optional, Tuple
from datetime import datetime


def _parse_tp_levels(tp_raw: Any) -> List[float]:
    """Parse take_profit field into list of TP prices."""
    if tp_raw is None:
        return []
    
    if isinstance(tp_raw, (int, float)):
        return [float(tp_raw)]
    
    if isinstance(tp_raw, list):
        try:
            return [float(x) for x in tp_raw if x is not None]
        except Exception:
            pass
    
    # Try JSON parsing
    try:
        s = str(tp_raw).strip()
        if s.startswith('['):
            data = json.loads(s)
            if isinstance(data, list):
                return [float(x) for x in data if x is not None]
        else:
            return [float(s)]
    except Exception:
        pass
    
    return []


def format_premium_signal(signal: DictType[str, Any]) -> str:
    """Format signal for PREMIUM tier - Shows TP1 & TP2 with confidence & validity."""
    
    lines = ["🚀 BUY SIGNAL" if signal.get("direction") == "long" else "🔴 SELL SIGNAL", ""]
    
    # Core info
    lines.extend([
        f"Asset: {signal.get('asset', 'N/A')}",
        f"Timeframe: {signal.get('timeframe', 'N/A')}",
    ])
    
    # Session if available
    session = signal.get('session') or signal.get('market_session', '')
    if session:
        lines.append(f"Session: {session}")
    
    lines.append("")
    
    # Entry levels
    entry = signal.get('entry')
    if entry:
        lines.append(f"Entry: {entry:,.4f}" if isinstance(entry, (int, float)) else f"Entry: {entry}")
    
    # Stop loss
    sl = signal.get('stop_loss')
    if sl:
        lines.append(f"Stop Loss: {sl:,.4f}" if isinstance(sl, (int, float)) else f"Stop Loss: {sl}")
    
    lines.append("")
    
    # Take profit levels (only TP1 & TP2 for Premium)
    tp_levels = _parse_tp_levels(signal.get('take_profit'))
    if tp_levels:
        if len(tp_levels) > 0:
            lines.append(f"TP1: {tp_levels[0]:,.4f}")
        if len(tp_levels) > 1:
            lines.append(f"TP2: {tp_levels[1]:,.4f}")
    
    lines.append("")
    
    # Confidence
    score = signal.get('score') or signal.get('confidence')
    if score:
        try:
            score_val = float(score)
            lines.append(f"🔥 Confidence: {score_val:.0f}%")
        except Exception:
            lines.append(f"🔥 Confidence: {score}%")
    
    # Validity / Expiration
    validity = signal.get('validity') or signal.get('expires_at')
    if validity:
        # If it's a candle count like "Next 2 candles"
        if 'candle' in str(validity).lower():
            lines.append(f"⏳ Validity: {validity}")
        else:
            lines.append(f"⏳ Validity: {validity}")
    
    lines.append("")
    lines.append("⚠️ Risk max 1–2%")
    
    return "\n".join(lines)


def format_vip_signal(signal: DictType[str, Any]) -> str:
    """Format signal for VIP tier - Complete details with all TPs, confluence, HTF bias, trade logic."""
    
    direction_emoji = "🚀" if signal.get("direction") == "long" else "🔴"
    direction_text = "BUY SIGNAL — VIP" if signal.get("direction") == "long" else "SELL SIGNAL — VIP"
    
    lines = [f"{direction_emoji} {direction_text}", ""]
    
    # Core info
    lines.extend([
        f"Asset: {signal.get('asset', 'N/A')}",
        f"Timeframe: {signal.get('timeframe', 'N/A')}",
    ])
    
    # Session
    session = signal.get('session') or signal.get('market_session', '')
    if session:
        lines.append(f"Session: {session}")
    
    # Market regime
    regime = signal.get('regime') or signal.get('market_regime', '')
    if regime:
        lines.append(f"Market Regime: {regime}")
    
    lines.append("")
    
    # Entry zone
    entry = signal.get('entry')
    entry_zone = signal.get('entry_zone') or signal.get('entry_zone_high')
    if entry and entry_zone:
        low = min(entry, entry_zone)
        high = max(entry, entry_zone)
        lines.append(f"Entry Zone: {low:,.4f} – {high:,.4f}")
    elif entry:
        lines.append(f"Entry Zone: {entry:,.4f}")
    
    # Stop loss
    sl = signal.get('stop_loss')
    if sl:
        lines.append(f"Stop Loss: {sl:,.4f}")
    
    lines.append("")
    
    # Take profit levels (all 3 for VIP)
    tp_levels = _parse_tp_levels(signal.get('take_profit'))
    if tp_levels:
        for i, tp in enumerate(tp_levels[:3], 1):
            lines.append(f"TP{i}: {tp:,.4f}")
    
    lines.append("")
    
    # Confluence score
    confluence = signal.get('confluence') or signal.get('confluence_score')
    if confluence:
        try:
            conf_val = float(confluence)
            lines.append(f"📊 Confluence Score: {conf_val:.0f} / 100")
        except Exception:
            lines.append(f"📊 Confluence Score: {confluence}")
    
    # Confidence level
    score = signal.get('score') or signal.get('confidence')
    if score:
        try:
            score_val = float(score)
            if score_val >= 90:
                conf_text = "🔥 VERY HIGH"
            elif score_val >= 75:
                conf_text = "✅ HIGH"
            else:
                conf_text = "📊 MODERATE"
            lines.append(f"🔥 Confidence: {conf_text}")
        except Exception:
            pass
    
    # HTF Bias
    htf_bias = signal.get('htf_bias') or signal.get('higher_timeframe_bias')
    if htf_bias:
        lines.append(f"📈 HTF Bias: {htf_bias}")
    
    # Risk-Reward
    rr = signal.get('risk_reward') or signal.get('rr_estimate')
    if rr:
        try:
            if isinstance(rr, str):
                lines.append(f"📊 Risk–Reward: {rr}")
            else:
                lines.append(f"📊 Risk–Reward: 1 : {float(rr):.2f}")
        except Exception:
            lines.append(f"📊 Risk–Reward: {rr}")
    
    lines.append("")
    
    # Invalidation levels
    invalidation = signal.get('invalidation') or signal.get('invalidation_level')
    if invalidation:
        lines.append("❌ Invalidation:")
        if isinstance(invalidation, list):
            for inv in invalidation:
                lines.append(f"• {inv}")
        elif isinstance(invalidation, str):
            if '\n' in invalidation:
                for line in invalidation.split('\n'):
                    if line.strip():
                        lines.append(f"• {line.strip()}")
            else:
                lines.append(f"• {invalidation}")
    
    lines.append("")
    
    # Trade logic
    trade_logic = signal.get('trade_logic') or signal.get('setup_rationale')
    if trade_logic:
        lines.append("🧠 Trade Logic:")
        if isinstance(trade_logic, list):
            for logic in trade_logic:
                lines.append(f"• {logic}")
        elif isinstance(trade_logic, str):
            if '\n' in trade_logic:
                for line in trade_logic.split('\n'):
                    if line.strip():
                        lines.append(f"• {line.strip()}")
            else:
                lines.append(f"• {trade_logic}")
    
    lines.append("")
    
    # Signal ID and version
    signal_id = signal.get('signal_id') or signal.get('id')
    if signal_id:
        lines.append(f"📌 Signal ID: {str(signal_id)[:16]}")
    
    version = signal.get('version') or signal.get('strategy_version')
    if version:
        lines.append(f"📈 Strategy Version: {version}")
    
    return "\n".join(lines)


def format_premium_tp_update(tp_level: int, asset: str, confidence: str = "HIGH") -> str:
    """Format PREMIUM tier TP hit update - Simple, concise."""
    
    emoji_map = {1: "✅", 2: "✅", 3: "✅"}
    emoji = emoji_map.get(tp_level, "✅")
    
    lines = [
        "📢 UPDATE — " + asset,
        "",
        f"{emoji} TP{tp_level} HIT",
        "🔒 Consider moving SL to breakeven",
    ]
    
    return "\n".join(lines)


def format_vip_tp_update(
    tp_level: int,
    asset: str,
    direction: str = "long",
    entry: Optional[float] = None,
    tp_price: Optional[float] = None,
    remaining_tps: Optional[List[float]] = None
) -> str:
    """Format VIP tier TP hit update - Detailed guidance."""
    
    emoji_map = {1: "🟢", 2: "🟡", 3: "🔴"}
    emoji = emoji_map.get(tp_level, "✅")
    
    lines = [
        f"📣 Outcome Update — {emoji} TP{tp_level} HIT",
        "",
        f"{asset}",
    ]
    
    # Profit calculation if we have price info
    if entry and tp_price:
        if direction.lower() == "long":
            profit_pct = ((tp_price - entry) / entry) * 100.0
        else:
            profit_pct = ((entry - tp_price) / entry) * 100.0
        
        lines.append(f"✅ Profit: +{profit_pct:.2f}%")
    
    lines.append("")
    
    # Guidance based on TP level
    if tp_level == 1:
        lines.extend([
            "💡 Partial TP1 hit — Consider:",
            "  • Move SL to breakeven",
            "  • Trail remaining position",
            "  • Target TP2 for more gains",
        ])
    elif tp_level == 2:
        lines.extend([
            "💡 Partial TP2 hit — Consider:",
            "  • Lock in more profits",
            "  • Exit 50% of position",
            "  • Trail the rest to TP3",
        ])
    elif tp_level == 3:
        lines.extend([
            "💡 TP3 hit — Consider:",
            "  • Exit remaining position",
            "  • Manage trailing stop",
            "  • Lock in full profit",
        ])
    
    # Show remaining TPs
    if remaining_tps:
        lines.append("")
        lines.append(f"📊 Remaining TPs: {' | '.join([f'TP{i} ${tp:,.2f}' for i, tp in enumerate(remaining_tps, tp_level + 1)])}")
    
    lines.append("")
    lines.append("This signal has been marked with an outcome in the tracker.")
    
    return "\n".join(lines)


def format_vip_no_trade_alert(conditions: DictType[str, Any]) -> str:
    """Format VIP NO-TRADE zone alert."""
    
    lines = [
        "🔵 VIP — NO-TRADE ALERT",
        "⛔ NO TRADE ZONE — VIP",
        "",
        "Market Conditions:",
    ]
    
    if conditions.get('low_volume'):
        lines.append("• Low volume")
    if conditions.get('choppy'):
        lines.append("• Choppy structure")
    if conditions.get('poor_rr'):
        lines.append("• Poor risk-to-reward")
    if conditions.get('high_volatility'):
        lines.append("• Extreme volatility")
    
    lines.extend([
        "",
        "📉 Capital preservation mode active",
    ])
    
    return "\n".join(lines)
