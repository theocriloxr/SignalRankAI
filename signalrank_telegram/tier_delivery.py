"""Tier-based signal delivery and routing manager.

Implements the GOLDEN RULE:
- VIP gets LESS noise, not more signals
- Premium gets MORE opportunity
- Free gets PROOF (attract users)
- Admin receives all signals
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from signalrank_telegram.formatter import (
    format_signal, format_signal_update_tp_hit,
    format_signal_no_trade_alert
)

class TierDeliveryManager:
    """
    Manages signal delivery based on user tier.

    GOLDEN RULE:
        - VIP gets LESS noise, not more signals (highest quality, most detail)
        - Premium gets MORE opportunity (medium+ quality, more signals)
        - Free gets PROOF (only best signals, attract users)
        - Admin receives all signals

    All delivery and formatting must use should_send_signal and format_for_delivery for:
        - Per-tier quality gates
        - Daily limits (DB-backed)
        - Persistent, idempotent delivery tracking (DB/Redis)
        - Retry-safe: duplicate sends are deduped at DB and memory level
        - Tier-appropriate message formatting (see formatter.py)
    """
    def __init__(self):
        """Initialize delivery manager."""
        self.delivery_log = []
    def should_send_signal(self, user_tier: str, score: float, user_id: Optional[str | int] = None, session=None) -> bool:
        """Check score eligibility for this tier.

        Daily limits are enforced by dispatch callers against Postgres delivery
        history so runtime memory usage stays low on constrained hosts.
        """
        import logging
        from core.tier_constants import TIER_SCORE_THRESHOLDS

        tier = str(user_tier or 'free').lower()

        # Quality gates (MUST pass)
        min_score = TIER_SCORE_THRESHOLDS.get(tier, 70)
        if score < min_score:
            if user_id is not None:
                logging.debug(f"[delivery] User {user_id} ({tier}) score {score} < {min_score}, not eligible.")
            return False
        
        return True

    async def should_send_signal_async(self, user_tier: str, score: float, user_id: Optional[str | int] = None, session=None) -> bool:
        """Async variant of should_send_signal for async contexts."""
        import logging
        from core.tier_constants import TIER_SCORE_THRESHOLDS

        tier = str(user_tier or 'free').lower()

        # Quality gates (MUST pass)
        min_score = TIER_SCORE_THRESHOLDS.get(tier, 70)
        if score < min_score:
            if user_id is not None:
                logging.debug(f"[delivery] User {user_id} ({tier}) score {score} < {min_score}, not eligible.")
            return False
        
        return True
    
    def format_for_delivery(self, signal: Dict, user_tier: str) -> Optional[str]:
        """Format signal for specific tier.
        
        Args:
            signal: Signal dict
            user_tier: User's subscription tier
        
        Returns:
            Formatted message string or None if filtered
        """
        # Check if signal passes quality gate
        score = float(signal.get('score', 0) or 0)
        if not self.should_send_signal(user_tier, score):
            return None
        
        # Format for tier
        return format_signal(signal, user_tier=user_tier)
    
    def get_users_for_signal(self, signal: Dict, signal_id: str, session=None) -> Dict[str, List[int]]:
        """
        Determine which users should receive this signal.
        
        Uses SignalDistributor to:
        - Prevent duplicate delivery (never same user+signal twice)
        - Respect daily limits per tier
        - Rate-limit per cycle (don't exhaust daily limit in one cycle)
        - Random sampling with even distribution
        
        Args:
            signal: Signal dict with 'score' field
            signal_id: Signal ID
            session: DB session for queries
        
        Returns:
            Dict mapping tier -> list of user_ids to send to
            Example: {'free': [u1, u2], 'premium': [u3, u4], 'vip': [u5], 'admin': [u6]}
        """
        if not session:
            from db.session import get_session
            session = get_session()
        
        from signalrank_telegram.signal_distribution import SignalDistributor
        
        distributor = SignalDistributor(session)
        recipients = distributor.sample_users_for_signal(signal, signal_id)
        
        return recipients
    
    def create_update_alert(self, signal: Dict, tp_number: int, user_tier: str) -> Optional[str]:
        """Create TP HIT update alert.
        
        Args:
            signal: Signal dict
            tp_number: Which TP was hit (1, 2, or 3)
            user_tier: User's tier
        
        Returns:
            Formatted update message or None
        """
        # Only send updates to PREMIUM+ (not FREE)
        if user_tier == 'free':
            return None
        
        return format_signal_update_tp_hit(signal, tp_number)
    
    def create_no_trade_alert(self, user_tier: str) -> Optional[str]:
        """Create NO-TRADE alert (VIP only).
        
        Args:
            user_tier: User's tier
        
        Returns:
            Formatted no-trade alert or None
        """
        # Only send to VIP
        if user_tier != 'vip':
            return None
        
        return format_signal_no_trade_alert()
    
    def get_tier_features(self, tier: str) -> Dict:
        """Get feature set for tier.
        
        Args:
            tier: User tier (free, premium, vip, admin)
        
        Returns:
            Dict of features for this tier
        """
        from core.tier_constants import TIER_SCORE_THRESHOLDS

        features_by_tier = {
            'free': {
                'signals_per_day': '1-3',
                'min_score': int(TIER_SCORE_THRESHOLDS.get('free', 80)),
                'multiple_tps': False,
                'confidence_percent': False,
                'validity_window': False,
                'updates': False,
                'session_tag': False,
                'market_regime': False,
                'confluence_breakdown': False,
                'invalidation_levels': False,
                'no_trade_alerts': False,
                'performance_stats': False,
                'priority_delivery': False,
            },
            'premium': {
                'signals_per_day': '5-10',
                'min_score': int(TIER_SCORE_THRESHOLDS.get('premium', 75)),
                'multiple_tps': True,      # 2-3 TP levels
                'confidence_percent': True, # % format
                'validity_window': True,
                'updates': True,            # Basic updates
                'session_tag': True,
                'market_regime': True,
                'confluence_breakdown': False,
                'invalidation_levels': False,
                'no_trade_alerts': False,
                'performance_stats': False,
                'priority_delivery': False,
            },
            'vip': {
                'signals_per_day': 'Quality-based',
                'min_score': int(TIER_SCORE_THRESHOLDS.get('vip', 75)),
                'multiple_tps': True,       # 3+ TP levels
                'confidence_percent': True, # Full score (0-100)
                'validity_window': True,
                'updates': True,            # Full updates
                'session_tag': True,
                'market_regime': True,
                'confluence_breakdown': True,
                'invalidation_levels': True,
                'no_trade_alerts': True,
                'performance_stats': True,  # Weekly
                'priority_delivery': True,
            },
            'admin': {
                'signals_per_day': 'All',
                'min_score': 0,
                'multiple_tps': True,
                'confidence_percent': True,
                'validity_window': True,
                'updates': True,
                'session_tag': True,
                'market_regime': True,
                'confluence_breakdown': True,
                'invalidation_levels': True,
                'no_trade_alerts': True,
                'performance_stats': True,
                'priority_delivery': True,
                'admin_info': True,
            },
        }
        return features_by_tier.get(tier.lower(), {})
    
    def get_max_tp_level_for_tier(self, tier: str) -> int:
        """Get maximum TP level user should see per tier.
        
        Args:
            tier: User tier (free, premium, vip, admin, owner)
        
        Returns:
            Max TP level (2 for FREE/PREMIUM, 3 for VIP/ADMIN/OWNER)
        """
        from core.tier_constants import TIER_SIGNAL_DEPTH
        depth = TIER_SIGNAL_DEPTH.get(tier.lower(), {})
        return depth.get('max_tp_level', 2)
    
    def should_show_upgrade_prompt(self, user_tier: str, signal: Dict, signal_count_today: int) -> bool:
        """Determine if FREE user should see upgrade prompt.
        
        Strategic: show on high-quality signals and every 3rd signal.
        
        Args:
            user_tier: User's tier
            signal: Signal dict
            signal_count_today: How many signals sent to user today
        
        Returns:
            True if should show prompt
        """
        from core.tier_constants import UPGRADE_PROMPT_FREQUENCY_INT
        
        if user_tier != 'free':
            return False
        
        score = float(signal.get('score', 0) or 0)
        
        # Show on every 3rd signal OR on high-quality signals (score >= 90)
        show_by_count = (signal_count_today + 1) % UPGRADE_PROMPT_FREQUENCY_INT == 0
        show_by_quality = score >= 90
        
        return show_by_count or show_by_quality
    
    def can_record_sl_outcome(
        self,
        signal_id: str,
        has_tp_been_hit: bool
    ) -> bool:
        """Check if SL outcome can be recorded for a signal.
        
        Once TP is hit, SL cannot be recorded (user closed position at TP).
        
        Args:
            signal_id: Signal ID
            has_tp_been_hit: Whether any TP (TP1/TP2/TP3) has been hit
        
        Returns:
            True if SL outcome can be recorded
        """
        return not has_tp_been_hit
    
    def format_outcome_for_tier(
        self,
        signal_id: str,
        outcome_type: str,  # 'tp1', 'tp2', 'tp3', 'sl'
        tp_count: Optional[int] = None,  # How many TPs hit so far (1, 2, 3)
        user_tier: str = 'free'
    ) -> Optional[str]:
        """Format outcome notification per tier.
        
        Args:
            signal_id: Signal ID
            outcome_type: Type of outcome (tp1, tp2, tp3, sl)
            tp_count: Number of TPs hit (for showing progress like '2/3 TP')
            user_tier: User's tier
        
        Returns:
            Formatted message or None if tier shouldn't see this outcome
        """
        max_tp = self.get_max_tp_level_for_tier(user_tier)
        
        # Suppress TP3 outcome for FREE/PREMIUM users
        if outcome_type == 'tp3' and max_tp < 3:
            return None
        
        # Format based on tier
        tier_lower = user_tier.lower()
        
        if outcome_type.startswith('tp'):
            tp_num = int(outcome_type[2])  # tp1 -> 1, tp2 -> 2, tp3 -> 3
            progress = f"{tp_count}" if tp_count else "?"
            
            if tier_lower in ('free', 'premium'):
                if tp_num > 2:
                    return None  # Don't show TP3
                msg = f"✅ Signal {signal_id[:8]}: TP{tp_num} hit ({progress}/2)"
                if tier_lower == 'free':
                    msg += "\n💡 Upgrade to Premium for full TP ladder"
            elif tier_lower in ('vip', 'admin', 'owner'):
                msg = f"✅ Signal {signal_id[:8]}: TP{tp_num} hit ({progress}/3)"
            else:
                msg = f"✅ TP{tp_num} hit"
            
            return msg
        
        elif outcome_type == 'sl':
            if tier_lower == 'free':
                msg = f"❌ Signal {signal_id[:8]}: SL hit\n💡 Upgrade to Premium for better signals"
            else:
                msg = f"❌ Signal {signal_id[:8]}: Stop Loss hit"
            return msg
        
        return None
    
    def log_delivery(self, signal_id: str, user_id: str, tier: str, delivered: bool, reason: str = ''):
        """Log signal delivery for tracking.
        
        Args:
            signal_id: Signal ID
            user_id: User ID
            tier: User tier
            delivered: Whether signal was delivered
            reason: Reason if not delivered
        """
        self.delivery_log.append({
            'timestamp': datetime.now(timezone.utc),
            'signal_id': signal_id,
            'user_id': user_id,
            'tier': tier,
            'delivered': delivered,
            'reason': reason,
        })
    
    def get_delivery_stats(self, days: int = 7) -> Dict:
        """Get delivery statistics.
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Dict with delivery stats
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent_logs = [log for log in self.delivery_log if log['timestamp'] >= cutoff]
        
        stats = {
            'total_attempts': len(recent_logs),
            'total_delivered': sum(1 for log in recent_logs if log['delivered']),
            'by_tier': {},
            'filter_reasons': {},
        }
        
        for log in recent_logs:
            tier = log['tier']
            if tier not in stats['by_tier']:
                stats['by_tier'][tier] = {'delivered': 0, 'filtered': 0}
            
            if log['delivered']:
                stats['by_tier'][tier]['delivered'] += 1
            else:
                stats['by_tier'][tier]['filtered'] += 1
                reason = log['reason']
                stats['filter_reasons'][reason] = stats['filter_reasons'].get(reason, 0) + 1
        
        return stats

# Global instance
_delivery_manager = TierDeliveryManager()

def get_delivery_manager() -> TierDeliveryManager:
    """Get global delivery manager instance."""
    return _delivery_manager
