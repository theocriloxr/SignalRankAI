"""
Tier-Based Notification System
- Premium/VIP: Detailed TP/SL advice, partial exit suggestions, position management
- Free: Basic TP/SL hit notifications only (for their 2 daily signals)
"""

import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TierNotificationManager:
    """Manages tier-based notifications."""
    
    def __init__(self):
        self.tier_limits = {
            'free': {
                'signals_per_day': 2,
                'detailed_notifications': False,
                'partial_exit_advice': False,
                'position_sizing': False,
                'win_rate_stats': False
            },
            'premium': {
                'signals_per_day': 20,
                'detailed_notifications': True,
                'partial_exit_advice': True,
                'position_sizing': True,
                'win_rate_stats': True
            },
            'vip': {
                'signals_per_day': 100,
                'detailed_notifications': True,
                'partial_exit_advice': True,
                'position_sizing': True,
                'win_rate_stats': True,
                'priority_support': True
            }
        }
    
    def format_new_signal(
        self,
        signal: Dict,
        user_tier: str,
        entry_zone: Dict,
        htf_bias: Dict,
        mtf_confluence: Dict,
        session: str
    ) -> str:
        """
        Format new signal alert based on user tier.
        
        Premium/VIP: Full details
        Free: Basic details
        """
        is_premium = user_tier in ['premium', 'vip']
        
        # Confidence badge
        score = signal.get('score', 0)
        if score >= 80:
            badge = "🔥 STRONG"
        elif score >= 60:
            badge = "⚠️ MODERATE"
        else:
            badge = "⚙️ WEAK"
        
        # Session emoji
        session_emoji = {
            'ASIA': '🌏',
            'LONDON': '🇬🇧',
            'NY': '🇺🇸',
            'LONDON_NY_OVERLAP': '🔥'
        }
        
        direction = signal.get('direction', 'long').upper()
        symbol = signal.get('symbol')
        timeframe = signal.get('timeframe', '1h')
        
        # Header
        msg = f"{badge} {direction} SIGNAL | {session_emoji.get(session, '')} {session.replace('_', ' ')}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📊 {symbol} | {timeframe}\n"
        
        # Entry zone
        zone_low = entry_zone.get('zone_low', 0)
        zone_high = entry_zone.get('zone_high', 0)
        current_price = signal.get('entry_price', 0)
        entry_status = entry_zone.get('status', 'WAIT')
        
        msg += f"Entry Zone: ${zone_low:,.2f} - ${zone_high:,.2f}\n"
        msg += f"Current: ${current_price:,.2f} {self._get_status_emoji(entry_status)}\n\n"
        
        # SL/TP
        sl_price = signal.get('sl_price', 0)
        sl_pct = signal.get('sl_pct', 0)
        
        msg += f"SL: ${sl_price:,.2f} ({sl_pct:+.2f}%)\n"
        
        # TP levels
        tp_levels = signal.get('tp_levels', [])
        for i, tp in enumerate(tp_levels, 1):
            tp_price = tp.get('price', 0)
            tp_pct = tp.get('pct', 0)
            
            if is_premium:
                exit_pct = tp.get('exit_percent', 33)
                msg += f"TP{i}: ${tp_price:,.2f} (+{tp_pct:.2f}%) → Exit {exit_pct}%\n"
            else:
                msg += f"TP{i}: ${tp_price:,.2f} (+{tp_pct:.2f}%)\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        # Details (Premium only)
        if is_premium:
            # Score & confluence
            confluence_count = signal.get('confluence_count', 0)
            confluence_total = signal.get('confluence_total', 5)
            msg += f"🎯 Score: {score}/100 | Confluence: {confluence_count}/{confluence_total} "
            msg += "✅\n" if confluence_count >= 4 else "⚠️\n"
            
            # HTF bias
            htf_tf = htf_bias.get('tf', '4h')
            htf_direction = htf_bias.get('bias', 'neutral').upper()
            htf_conf = htf_bias.get('confidence', 0)
            msg += f"📈 HTF Bias: {htf_direction} ({htf_tf}, {htf_conf}% conf)\n"
            
            # MTF alignment
            aligned = mtf_confluence.get('score', 0)
            msg += f"📊 MTF Alignment: {aligned}% of timeframes aligned\n"
            
            # R:R and risk
            rr_ratio = signal.get('rr_ratio', 0)
            risk_pct = signal.get('risk_pct', 5)
            risk_amount = signal.get('suggested_risk_amount', 0)
            
            msg += f"💪 R:R: {rr_ratio:.1f}:1 | Risk: {risk_pct}% (${risk_amount:,.0f})\n\n"
            
            # Position sizing suggestion
            position_size = signal.get('position_size', 0)
            msg += f"💼 Suggested Position: {position_size:,.4f} units\n\n"
            
            # Reason
            reason = signal.get('reason', 'Multiple confluence factors')
            msg += f"Reason: {reason}\n\n"
            
            # Validity
            expires_at = signal.get('expires_at')
            if expires_at:
                msg += f"⚠️ Valid for: {self._format_time_remaining(expires_at)}\n"
            
            invalidate_price = signal.get('invalid_if_price')
            if invalidate_price:
                msg += f"❌ Invalidate if: Price closes "
                if direction == 'LONG':
                    msg += f"below ${invalidate_price:,.2f}\n"
                else:
                    msg += f"above ${invalidate_price:,.2f}\n"
        
        else:
            # Free tier - minimal info
            msg += f"Score: {score}/100\n"
            msg += f"R:R: {signal.get('rr_ratio', 0):.1f}:1\n"
        
        # Signal ID
        signal_id = signal.get('id', 'N/A')
        msg += f"\n📋 Ref: {signal_id[:8]}\n"
        
        return msg
    
    def format_tp_hit_notification(
        self,
        signal: Dict,
        user_tier: str,
        tp_level: int,
        current_profit_pct: float,
        current_market_price: float = None
    ) -> str:
        """
        Enhanced TP hit notification: includes full signal data, which TP was hit, current market price, and partial profit advice.
        """
        is_premium = user_tier in ['premium', 'vip', 'admin', 'owner']
        symbol = signal.get('symbol')
        direction = signal.get('direction', '').upper()
        entry = signal.get('entry')
        stop = signal.get('stop') or signal.get('stop_loss') or signal.get('sl')
        tps = signal.get('targets') or signal.get('tp_levels') or []
        if isinstance(tps, (float, int)):
            tps = [tps]
        timeframe = signal.get('timeframe', '')
        msg = f"🎯 TP{tp_level} HIT: {symbol} ({timeframe})\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"Direction: {direction}\nEntry: {entry}\nStop Loss: {stop}\n"
        if tps:
            for i, tp in enumerate(tps, 1):
                if isinstance(tp, dict):
                    price = tp.get('price', tp.get('tp', ''))
                else:
                    price = tp
                msg += f"TP{i}: {price}\n"
        msg += f"\nTP HIT: TP{tp_level}\n"
        if current_market_price is not None:
            msg += f"Current Market Price: {current_market_price}\n"
        msg += f"Profit: +{current_profit_pct:.2f}%\n"
        # Partial profit advice
        if is_premium:
            percent = 33 if tp_level == 1 else 50 if tp_level == 2 else 100
            msg += f"\n💡 Suggestion: Take {percent}% partial profit at TP{tp_level}."
            if tp_level == 1:
                msg += " Move SL to break-even."
            elif tp_level == 2:
                msg += " Tighten SL to TP1 level."
            elif tp_level == 3:
                msg += " Consider closing the rest of your position."
        else:
            msg += "\nUpgrade to Premium for detailed advice."
        # Remaining TPs
        if tps and tp_level < len(tps):
            remaining_tps = []
            for i, tp in enumerate(tps, 1):
                if i > tp_level:
                    price = tp.get('price', tp.get('tp', '')) if isinstance(tp, dict) else tp
                    remaining_tps.append(f"TP{i} {price}")
            if remaining_tps:
                msg += f"\n📊 Remaining TPs: {' | '.join(remaining_tps)}"
        msg += f"\n\n📋 Ref: {signal.get('id', 'N/A')[:8]}"
        return msg
    
    def format_sl_hit_notification(
        self,
        signal: Dict,
        user_tier: str,
        loss_pct: float
    ) -> str:
        """
        Format SL hit notification.
        
        Premium: Analysis + advice
        Free: Basic notification
        """
        is_premium = user_tier in ['premium', 'vip']
        
        symbol = signal.get('symbol')
        
        if is_premium:
            msg = f"🛑 STOP LOSS HIT: {symbol}\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"Loss: {loss_pct:.2f}%\n\n"
            
            # Brief analysis
            msg += "💡 Analysis:\n"
            msg += "- Risk management protected capital\n"
            msg += "- Wait for new setup before re-entering\n"
            msg += "- Review market conditions\n"
            
            msg += f"\n📋 Ref: {signal.get('id', 'N/A')[:8]}"
        
        else:
            # Free tier
            msg = f"❌ SL HIT: {symbol} ({loss_pct:.2f}%)"
        
        return msg
    
    def format_signal_update(
        self,
        signal: Dict,
        user_tier: str,
        update_type: str,
        update_data: Dict
    ) -> str:
        """
        Format signal update notification.
        
        Updates: 
        - SL moved to break-even
        - Trailing stop activated
        - Signal invalidated
        - HTF bias flip
        
        Premium only.
        """
        if user_tier not in ['premium', 'vip']:
            return ""  # No updates for free tier
        
        symbol = signal.get('symbol')
        
        if update_type == 'sl_to_breakeven':
            msg = f"🔒 BREAK-EVEN: {symbol}\n"
            msg += "Stop loss moved to entry price.\n"
            msg += "Risk eliminated - position now risk-free!\n"
        
        elif update_type == 'trailing_stop':
            new_sl = update_data.get('new_sl', 0)
            profit_locked = update_data.get('profit_locked_pct', 0)
            msg = f"📈 TRAILING STOP: {symbol}\n"
            msg += f"SL moved to ${new_sl:,.2f}\n"
            msg += f"Profit locked: +{profit_locked:.2f}%\n"
        
        elif update_type == 'invalidated':
            reason = update_data.get('reason', 'Unknown')
            msg = f"❌ SIGNAL INVALIDATED: {symbol}\n"
            msg += f"Reason: {reason}\n"
            msg += "Exit position if still holding.\n"
        
        elif update_type == 'htf_bias_flip':
            old_bias = update_data.get('old_bias', 'N/A')
            new_bias = update_data.get('new_bias', 'N/A')
            msg = f"⚠️ HTF BIAS FLIP: {symbol}\n"
            msg += f"Changed: {old_bias} → {new_bias}\n"
            msg += "Consider reducing position size.\n"
        
        else:
            msg = f"ℹ️ UPDATE: {symbol}\n"
            msg += str(update_data)
        
        msg += f"\n📋 Ref: {signal.get('id', 'N/A')[:8]}"
        return msg
    
    def format_no_trade_alert(
        self,
        reasons: List[str],
        session: str
    ) -> str:
        """
        Format NO TRADE alert.
        
        Sent to all tiers.
        """
        msg = "⚠️ NO TRADE ALERT\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "Market conditions not ideal:\n\n"
        
        for reason in reasons:
            msg += f"• {reason}\n"
        
        msg += f"\n📊 Session: {session}\n"
        msg += "\n💡 Recommendation: Wait for better setup"
        
        return msg
    
    def format_performance_update(
        self,
        user_tier: str,
        stats: Dict
    ) -> str:
        """
        Format performance stats update.
        
        Premium only.
        """
        if user_tier not in ['premium', 'vip']:
            return ""
        
        msg = "📊 PERFORMANCE UPDATE\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        win_rate = stats.get('win_rate', 0)
        total_signals = stats.get('total_signals', 0)
        wins = stats.get('wins', 0)
        losses = stats.get('losses', 0)
        
        msg += f"Win Rate: {win_rate:.1f}% ({wins}W / {losses}L)\n"
        msg += f"Total Signals: {total_signals}\n\n"
        
        # Top pairs
        top_pairs = stats.get('top_pairs', [])
        if top_pairs:
            msg += "🏆 Top Performers:\n"
            for pair in top_pairs[:3]:
                msg += f"• {pair['symbol']}: {pair['win_rate']:.0f}%\n"
        
        # Worst pairs
        worst_pairs = stats.get('worst_pairs', [])
        if worst_pairs:
            msg += "\n⚠️ Avoid:\n"
            for pair in worst_pairs[:2]:
                msg += f"• {pair['symbol']}: {pair['win_rate']:.0f}%\n"
        
        return msg
    
    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for entry status."""
        if 'BUY' in status:
            return '✅ BUY'
        elif 'SELL' in status:
            return '✅ SELL'
        else:
            return '⏳ WAIT'
    
    def _format_time_remaining(self, expires_at: datetime) -> str:
        """Format time remaining until expiration."""
        remaining = expires_at - datetime.utcnow()
        
        if remaining.total_seconds() < 0:
            return "EXPIRED"
        
        minutes = int(remaining.total_seconds() / 60)
        
        if minutes < 60:
            return f"{minutes}m"
        else:
            hours = minutes // 60
            return f"{hours}h"
