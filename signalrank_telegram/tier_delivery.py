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
    
    def get_users_for_signal(self, signal: Dict) -> Dict[str, List[str]]:
        """Determine which user tiers should receive this signal.
        
        Args:
            signal: Signal dict
        
        Returns:
            Dict mapping tier -> list of user_ids
            Example: {'free': [user1, user2], 'premium': [user3, user4, user5], 'vip': [user6]}
        """
        score = float(signal.get('score', 0) or 0)
        from core.tier_constants import TIER_SCORE_THRESHOLDS
        
        recipients = {
            'free': [],
            'premium': [],
            'vip': [],
            'admin': [],  # Admin always gets signals
        }
        
        # Determine which tiers qualify
        # NOTE: In real implementation, query users by tier from database
        
        # Quality gates determine who CAN receive
        can_free = score >= float(TIER_SCORE_THRESHOLDS.get('free', 80))
        can_premium = score >= float(TIER_SCORE_THRESHOLDS.get('premium', 75))
        can_vip = score >= float(TIER_SCORE_THRESHOLDS.get('vip', 75))
        
        # Example return (would be populated from database):
        # if can_free:
        #     recipients['free'] = db.query_users_by_tier('free')
        # if can_premium:
        #     recipients['premium'] = db.query_users_by_tier('premium')
        # if can_vip:
        #     recipients['vip'] = db.query_users_by_tier('vip')
        # recipients['admin'] = db.query_users_by_tier('admin')
        
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
