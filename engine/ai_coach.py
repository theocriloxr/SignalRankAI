"""
AI Coach
Phase 4.2 - Trade Analysis & Improvement Suggestions

Commands: /coach
Explains: Why trade won, Why trade lost, How to improve
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TradeAnalysis:
    """Analysis of a single trade."""
    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    result: str  # 'win', 'loss', 'breakeven'
    pnl_pct: float
    holding_time: timedelta
    regime: str
    timeframe: str
    
    @property
    def r_multiples(self) -> float:
        """R multiple (risk units)."""
        if self.direction == 'long':
            risk = self.entry_price - self.stop_loss
            if risk <= 0:
                return 0
            return (self.exit_price - self.entry_price) / risk
        else:
            risk = self.stop_loss - self.entry_price
            if risk <= 0:
                return 0
            return (self.entry_price - self.exit_price) / risk


class AICoach:
    """AI-powered trading coach."""
    
    def __init__(self):
        self.trade_history: List[TradeAnalysis] = []
    
    def add_trade(
        self,
        signal_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        stop_loss: float,
        take_profit: float,
        holding_time: timedelta,
        regime: str,
        timeframe: str,
    ) -> None:
        """Add a completed trade for analysis."""
        # Determine result
        if direction == 'long':
            pnl = (exit_price - entry_price) / entry_price * 100
        else:
            pnl = (entry_price - exit_price) / entry_price * 100
        
        result = 'breakeven'
        if pnl > 0.5:
            result = 'win'
        elif pnl < -0.5:
            result = 'loss'
        
        analysis = TradeAnalysis(
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            result=result,
            pnl_pct=pnl,
            holding_time=holding_time,
            regime=regime,
            timeframe=timeframe,
        )
        
        self.trade_history.append(analysis)
    
    def analyze_win(self, trade: TradeAnalysis) -> List[str]:
        """Analyze why a trade won."""
        insights = []
        
        # R multiple analysis
        r = trade.r_multiples
        if r >= 3:
            insights.append(f"🎯 Excellent R:R - {r:.1f}R multiple achieved")
        elif r >= 2:
            insights.append(f"✅ Good R:R - {r:.1f}R multiple")
        elif r >= 1:
            insights.append(f"📈 Profitable - {r:.1f}R")
        
        # Holding time analysis
        hours = trade.holding_time.total_seconds() / 3600
        if hours < 1:
            insights.append("⚡ Quick profit - strong momentum")
        elif hours > 48:
            insights.append(f"📅 Held {hours:.0f}h - positional patience")
        
        # Regime match
        if trade.regime == 'TRENDING' and trade.result == 'win':
            insights.append("🟢 Correct regime - TRENDING aligned with direction")
        elif trade.regime == 'RANGING' and trade.result == 'win':
            insights.append("🎯 Mean reversion worked in ranging market")
        
        return insights
    
    def analyze_loss(self, trade: TradeAnalysis) -> List[str]:
        """Analyze why a trade lost."""
        insights = []
        
        # Risk analysis
        r = trade.r_multiples
        if r <= -2:
            insights.append(f"⚠️ Large loss - {abs(r):.1f}R below entry")
        elif r <= -1:
            insights.append(f"❌ Stop hit - {abs(r):.1f}R loss")
        
        # Timing issues
        hours = trade.holding_time.total_seconds() / 3600
        if hours < 0.5:
            insights.append("⏱️ Stopped too fast - consider wider stops")
        elif hours > 72:
            insights.append("📅 Held too long - consider time-based exits")
        
        # Regime mismatch detection
        if trade.regime == 'TRENDING' and trade.direction == 'short':
            insights.append("🔴 Counter-trend - fighting the trend")
        elif trade.regime == 'RANGING' and trade.direction in ['long', 'short']:
            insights.append("📊 Breakout failed - was market ranging?")
        
        return insights
    
    def get_improvement_tips(self) -> List[str]:
        """Get general improvement suggestions."""
        if not self.trade_history:
            return ["📝 Complete more trades for analysis"]
        
        wins = [t for t in self.trade_history if t.result == 'win']
        losses = [t for t in self.trade_history if t.result == 'loss']
        
        tips = []
        
        # Win rate analysis
        win_rate = len(wins) / len(self.trade_history) * 100
        if win_rate < 40:
            tips.append("📉 Win rate below 40% - review entry criteria")
        elif win_rate > 60:
            tips.append("📈 Strong win rate maintained")
        
        # Average R analysis
        if wins:
            avg_r = sum(t.r_multiples for t in wins) / len(wins)
            if avg_r < 1.5:
                tips.append("⚠️ Avg R on wins is low - consider taking more off table")
        
        # Time-based patterns
        if losses:
            avg_loss_time = sum(t.holding_time.total_seconds() / 3600 for t in losses) / len(losses)
            if avg_loss_time < 1:
                tips.append("⏱️ Losses happen fast - tighten entry confirmation")
        
        # Regime-specific tips
        recent_regimes = [t.regime for t in self.trade_history[-10:]]
        if 'RANGING' in recent_regimes and len([t for t in losses if t.regime == 'RANGING']) > 2:
            tips.append("📊 Struggling in RANGING - use mean reversion strategy")
        
        if 'TRENDING' in recent_regimes and len([t for t in losses if t.regime == 'TRENDING']) > 2:
            tips.append("📈 Struggling in TRENDING - check trend confirmation")
        
        return tips
    
    def get_coach_message(self, days: int = 7) -> str:
        """Get coach analysis message."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        
        # Filter recent trades
        recent = [t for t in self.trade_history if t.holding_time.total_seconds() > 0]
        
        if not recent:
            return (
                "👨‍🏫 <b>AI Coach</b>\n\n"
                "No trades to analyze yet.\n"
                "Complete trades to receive personalized coaching."
            )
        
        # Analyze recent trades
        wins = [t for t in recent if t.result == 'win']
        losses = [t for t in recent if t.result == 'loss']
        
        lines = [
            "👨‍🏫 <b>AI Coach</b>",
            f"📊 Last {days} days: {len(recent)} trades",
            f"  Wins: {len(wins)} | Losses: {len(losses)}",
            "",
        ]
        
        # Recent wins analysis
        if wins:
            lines.append("<b>✅ Recent Wins:</b>")
            for trade in wins[-3:]:
                insights = self.analyze_win(trade)
                lines.append(f"  {trade.symbol} ({trade.direction}):")
                for insight in insights:
                    lines.append(f"    {insight}")
            lines.append("")
        
        # Recent losses analysis
        if losses:
            lines.append("<b>❌ Recent Losses:</b>")
            for trade in losses[-3:]:
                insights = self.analyze_loss(trade)
                lines.append(f"  {trade.symbol} ({trade.direction}):")
                for insight in insights:
                    lines.append(f"    {insight}")
            lines.append("")
        
        # Improvement tips
        tips = self.get_improvement_tips()
        if tips:
            lines.append("<b>💡 Improvement Tips:</b>")
            for tip in tips:
                lines.append(f"  {tip}")
        
        # Overall assessment
        win_rate = len(wins) / len(recent) * 100 if recent else 0
        if win_rate >= 60:
            lines.append("\n🌟 <b>Overall: Strong performance!</b>")
        elif win_rate >= 40:
            lines.append("\n📈 <b>Overall: Steady progress</b>")
        else:
            lines.append("\n⚠️ <b>Overall: Needs improvement</b>")
        
        return "\n".join(lines)


# Singleton
_coach: Optional[AICoach] = None


def get_ai_coach() -> AICoach:
    """Get global AI coach."""
    global _coach
    if _coach is None:
        _coach = AICoach()
    return _coach


def format_coach(days: int = 7) -> str:
    """Convenience function."""
    return get_ai_coach().get_coach_message(days=days)
