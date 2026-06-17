"""
SignalOrchestrator - Professional-grade signal delivery with state management.

This module implements:
1. is_significant_update() - Compare signal states to determine if update is warranted
2. SignalOrchestrator class - Manage signal lifecycle with editMessageText support
3. Cooldown registry per signal_id to prevent spam

Fixes the "repeating signals" issue by:
- Tracking previous signal state per signal_id
- Using editMessageText for updates instead of new messages
- Adding cooldown per signal_id
"""

import json
import time
import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Cooldown settings
SIGNAL_NOTIFY_COOLDOWN_SECONDS = 900  # 15 minutes default
SIGNAL_NOTIFY_COOLDOWN_KEY = "signalrankai:signal_cooldown:"
SIGNAL_STATE_KEY = "signalrankai:signal_state:"

# Significance threshold - changes below this % are considered insignificant
DEFAULT_SIGNIFICANCE_THRESHOLD_PCT = 0.1  # 0.1%


def is_significant_update(old_signal: Dict[str, Any], new_signal: Dict[str, Any], threshold_pct: float = DEFAULT_SIGNIFICANCE_THRESHOLD_PCT) -> bool:
    """
    Compare two signal states to determine if update is significant.
    
    Args:
        old_signal: Previous signal state with keys like entry, stop_loss, take_profit, etc.
        new_signal: New signal state to compare
        threshold_pct: Minimum % change to consider significant (default 0.1%)
    
    Returns:
        True if changes justify sending an update notification
    
    Examples:
        >>> old = {'entry': 201.634, 'stop_loss': 201.464, 'take_profit': 202.5}
        >>> new = {'entry': 201.625, 'stop_loss': 201.464, 'take_profit': 202.5}
        >>> is_significant_update(old, new, 0.1)
        True  # Entry changed by 0.009 (~0.0045%) - below threshold
        
        >>> new2 = {'entry': 201.500, 'stop_loss': 201.464, 'take_profit': 202.5}
        >>> is_significant_update(old, new2, 0.1)
        True  # Entry changed by 0.134 (~0.066%) - above threshold
    """
    if not old_signal or not new_signal:
        logger.warning("[orchestrator] is_significant_update called with empty signal")
        return True  # Default to significant if cannot compare
    
    threshold = threshold_pct / 100.0  # Convert to decimal
    
    # Check direction change - always significant
    old_direction = str(old_signal.get('direction') or old_signal.get('side') or '').lower().strip()
    new_direction = str(new_signal.get('direction') or new_signal.get('side') or '').lower().strip()
    if old_direction != new_direction:
        logger.info(f"[orchestrator] Direction changed: {old_direction} -> {new_direction}")
        return True
    
    # Check entry price change
    old_entry = _safe_float(old_signal.get('entry'))
    new_entry = _safe_float(new_signal.get('entry'))
    if old_entry > 0 and new_entry > 0:
        entry_change_pct = abs(new_entry - old_entry) / old_entry
        if entry_change_pct > threshold:
            logger.info(f"[orchestrator] Entry changed by {entry_change_pct*100:.3f}% (threshold: {threshold_pct}%)")
            return True
    
    # Check stop loss change
    old_sl = _safe_float(old_signal.get('stop_loss') or old_signal.get('stop'))
    new_sl = _safe_float(new_signal.get('stop_loss') or new_signal.get('stop'))
    if old_sl > 0 and new_sl > 0:
        sl_change_pct = abs(new_sl - old_sl) / old_sl
        if sl_change_pct > threshold:
            logger.info(f"[orchestrator] Stop loss changed by {sl_change_pct*100:.3f}%")
            return True
    
    # Check take profit changes
    old_tp = old_signal.get('take_profit') or old_signal.get('targets') or []
    new_tp = new_signal.get('take_profit') or new_signal.get('targets') or []
    
    # Handle both list and single value formats
    if isinstance(old_tp, (list, tuple)) and isinstance(new_tp, (list, tuple)):
        # Compare each TP level
        for i in range(min(len(old_tp), len(new_tp))):
            old_tp_val = _safe_float(old_tp[i]) if i < len(old_tp) else 0
            new_tp_val = _safe_float(new_tp[i]) if i < len(new_tp) else 0
            if old_tp_val > 0 and new_tp_val > 0:
                tp_change_pct = abs(new_tp_val - old_tp_val) / old_tp_val
                if tp_change_pct > threshold:
                    logger.info(f"[orchestrator] TP{i+1} changed by {tp_change_pct*100:.3f}%")
                    return True
    elif isinstance(old_tp, (list, tuple)) and not isinstance(new_tp, (list, tuple)):
        # TP changed from list to single value - significant
        return True
    elif not isinstance(old_tp, (list, tuple)) and isinstance(new_tp, (list, tuple)):
        # TP changed from single to list - significant
        return True
    else:
        # Both single values
        old_tp_val = _safe_float(old_tp)
        new_tp_val = _safe_float(new_tp)
        if old_tp_val > 0 and new_tp_val > 0:
            tp_change_pct = abs(new_tp_val - old_tp_val) / old_tp_val
            if tp_change_pct > threshold:
                logger.info(f"[orchestrator] TP changed by {tp_change_pct*100:.3f}%")
                return True
    
    # No significant changes found
    logger.debug(f"[orchestrator] No significant changes detected")
    return False


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class SignalOrchestrator:
    """
    Manages signal lifecycle with state tracking and message editing.
    
    This replaces the "send-and-forget" model with stateful event-driven architecture.
    """
    
    def __init__(self, redis_state=None):
        """
        Initialize the orchestrator.
        
        Args:
            redis_state: Optional RedisState instance for persistence
        """
        self._state = redis_state
        self._cooldown_seconds = SIGNAL_NOTIFY_COOLDOWN_SECONDS
        
        # Import config for settings
        try:
            from config import config
            self._cooldown_seconds = getattr(config, 'SIGNAL_NOTIFY_COOLDOWN_SECONDS', SIGNAL_NOTIFY_COOLDOWN_SECONDS)
        except Exception:
            pass
    
    def get_signal_state(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """
        Get previous signal state from cache.
        
        Args:
            signal_id: Unique signal identifier
        
        Returns:
            Previous signal state dict or None if not found
        """
        if not self._state:
            return None
        
        try:
            key = f"{SIGNAL_STATE_KEY}{signal_id}"
            state_json = self._state.cache_get_sync(key)
            if state_json:
                return json.loads(state_json)
        except Exception as e:
            logger.debug(f"[orchestrator] Failed to get signal state: {e}")
        
        return None
    
    def set_signal_state(self, signal_id: str, state: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        """
        Cache signal state for future comparison.
        
        Args:
            signal_id: Unique signal identifier
            state: Signal state dict to cache
            ttl_seconds: Optional TTL override
        """
        if not self._state:
            return
        
        try:
            key = f"{SIGNAL_STATE_KEY}{signal_id}"
            ttl = ttl_seconds or self._cooldown_seconds
            self._state.cache_set_sync(key, json.dumps(state), ttl)
            logger.debug(f"[orchestrator] Cached signal state for {signal_id}")
        except Exception as e:
            logger.debug(f"[orchestrator] Failed to set signal state: {e}")
    
    def check_cooldown(self, signal_id: str) -> bool:
        """
        Check if signal is in cooldown period.
        
        Args:
            signal_id: Unique signal identifier
        
        Returns:
            True if cooldown active (should suppress notification)
        """
        if not self._state:
            return False
        
        try:
            key = f"{SIGNAL_NOTIFY_COOLDOWN_KEY}{signal_id}"
            remaining = self._state.cache_get_sync(key)
            if remaining:
                logger.info(f"[orchestrator] Signal {signal_id} in cooldown: {remaining}")
                return True
        except Exception as e:
            logger.debug(f"[orchestrator] Failed to check cooldown: {e}")
        
        return False
    
    def set_cooldown(self, signal_id: str, ttl_seconds: Optional[int] = None) -> None:
        """
        Set cooldown for signal_id.
        
        Args:
            signal_id: Unique signal identifier
            ttl_seconds: Optional TTL override (default: 15 minutes)
        """
        if not self._state:
            return
        
        try:
            key = f"{SIGNAL_NOTIFY_COOLDOWN_KEY}{signal_id}"
            ttl = ttl_seconds or self._cooldown_seconds
            # Store timestamp as value for debugging
            self._state.cache_set_sync(key, str(time.time()), ttl)
            logger.info(f"[orchestrator] Set cooldown for {signal_id}: {ttl}s")
        except Exception as e:
            logger.debug(f"[orchestrator] Failed to set cooldown: {e}")
    
    async def dispatch_signal(
        self, 
        signal_data: Dict[str, Any], 
        chat_id: int, 
        existing_message_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Determine whether to create new message or edit existing.
        
        Args:
            signal_data: New signal data dict
            chat_id: Target chat ID
            existing_message_id: Optional existing message ID to edit
        
        Returns:
            Dict with keys:
                - action: 'new', 'edit', or 'suppress'
                - message_id: Telegram message ID to use
                - reason: Description of action taken
        """
        signal_id = signal_data.get('signal_id') or signal_data.get('id')
        if not signal_id:
            return {
                'action': 'new',
                'message_id': None,
                'reason': 'no_signal_id'
            }
        
        # Check cooldown first
        if self.check_cooldown(signal_id):
            return {
                'action': 'suppress',
                'message_id': existing_message_id,
                'reason': f'cooldown_active_{self._cooldown_seconds}s'
            }
        
        # Get previous state for comparison
        old_state = self.get_signal_state(signal_id)
        
        if old_state and existing_message_id:
            # Compare with previous state
            if is_significant_update(old_state, signal_data):
                # Significant change - update the message
                self.set_signal_state(signal_id, signal_data)
                self.set_cooldown(signal_id)
                
                return {
                    'action': 'edit',
                    'message_id': existing_message_id,
                    'reason': 'significant_update'
                }
            else:
                # No significant change - suppress but update state
                self.set_signal_state(signal_id, signal_data)
                
                return {
                    'action': 'suppress',
                    'message_id': existing_message_id,
                    'reason': 'no_significant_change'
                }
        elif existing_message_id:
            # Has existing message but no previous state - treat as update
            self.set_signal_state(signal_id, signal_data)
            self.set_cooldown(signal_id)
            
            return {
                'action': 'edit',
                'message_id': existing_message_id,
                'reason': 'initial_update'
            }
        else:
            # No existing message - send new
            self.set_signal_state(signal_id, signal_data)
            self.set_cooldown(signal_id)
            
            return {
                'action': 'new',
                'message_id': None,
                'reason': 'new_signal'
            }


# Singleton instance
_orchestrator_instance: Optional[SignalOrchestrator] = None


def get_signal_orchestrator() -> SignalOrchestrator:
    """Get or create the SignalOrchestrator singleton."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        try:
            from core.redis_state import state
            _orchestrator_instance = SignalOrchestrator(redis_state=state)
        except Exception as e:
            logger.warning(f"[orchestrator] Failed to initialize with Redis: {e}")
            _orchestrator_instance = SignalOrchestrator()
    return _orchestrator_instance


# Backwards compatibility
orchestrator = get_signal_orchestrator()


__all__ = [
    'is_significant_update',
    'SignalOrchestrator',
    'get_signal_orchestrator',
    'orchestrator',
]
