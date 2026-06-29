"""
Provider Health Monitoring and Auto-Failover for SignalRankAI.

This module monitors data provider health and automatically switches
providers when one is throttled or fails.

Features:
- Track success/failure rates per provider
- Automatic cooldown when rate limited (429 errors)
- Round-robin or priority-based provider switching
- Health alerts to admins

Usage:
    registry = ProviderRegistry()
    
    # Get a healthy provider for an asset
    provider = await registry.get_provider("BTCUSDT")
    
    # Report a failure
    await registry.report_failure("polygon", "rate_limited")
    
    # Report success
    await registry.report_success("polygon")
"""

import os
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

# Default providers
DEFAULT_PROVIDERS = [
    "polygon",
    "yfinance", 
    "tradingview",
    "binance",
]

# Cooldown duration when rate limited (seconds)
DEFAULT_COOLDOWN_SECONDS = 60


class ProviderHealth:
    """Health status for a single provider."""
    
    def __init__(self, name: str):
        self.name = name
        self.is_active = True
        self.is_healthy = True
        self.fail_count = 0
        self.success_count = 0
        self.last_checked: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.cooldown_until: Optional[datetime] = None
        self.metadata: Dict[str, Any] = {}
    
    def is_available(self) -> bool:
        """Check if provider is currently available."""
        if not self.is_active:
            return False
        
        if self.cooldown_until and datetime.utcnow() < self.cooldown_until:
            return False
        
        return True
    
    def get_success_rate(self) -> float:
        """Get success rate as percentage."""
        total = self.success_count + self.fail_count
        if total == 0:
            return 100.0
        return (self.success_count / total) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "is_active": self.is_active,
            "is_healthy": self.is_healthy,
            "is_available": self.is_available(),
            "fail_count": self.fail_count,
            "success_count": self.success_count,
            "success_rate": self.get_success_rate(),
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "last_error": self.last_error,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
        }


class ProviderRegistry:
    """
    Registry for managing data provider health and failover.
    
    This ensures the engine never fails due to a single provider being down.
    When one provider is rate-limited, it automatically switches to another.
    
    Usage:
        registry = ProviderRegistry()
        
        # Initialize with available providers
        await registry.initialize(["polygon", "yfinance", "tradingview"])
        
        # Get provider for an asset
        provider = await registry.get_provider("BTCUSDT")
        
        # Report result
        if success:
            await registry.report_success(provider)
        else:
            await registry.report_failure(provider, error_code)
    """
    
    def __init__(self):
        self._providers: Dict[str, ProviderHealth] = {}
        self._redis = None
        self._redis_url = self._resolve_redis_url()
        self._cooldown_seconds = int(
            os.getenv("PROVIDER_COOLDOWN_SECONDS", str(DEFAULT_COOLDOWN_SECONDS))
        )
        
        if self._redis_url:
            self._init_redis()
    
    def _resolve_redis_url(self) -> Optional[str]:
        return os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL") or None
    
    def _init_redis(self):
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._redis.ping()
            logger.info("[provider_registry] Connected to Redis")
        except Exception as e:
            logger.debug(f"[provider_registry] Redis unavailable: {e}")
            self._redis = None
    
    async def initialize(self, providers: Optional[List[str]] = None) -> None:
        """Initialize the provider registry with available providers."""
        if providers is None:
            providers = DEFAULT_PROVIDERS
        
        for name in providers:
            if name not in self._providers:
                self._providers[name] = ProviderHealth(name)
        
        # Also load from Redis if available
        if self._redis:
            try:
                for name in providers:
                    data = self._redis.hget("provider_health", name)
                    if data:
                        import json
                        info = json.loads(data)
                        if name in self._providers:
                            self._providers[name].fail_count = info.get("fail_count", 0)
                            self._providers[name].success_count = info.get("success_count", 0)
                            self._providers[name].is_active = info.get("is_active", True)
            except Exception:
                pass
        
        logger.info(f"[provider_registry] Initialized with providers: {list(self._providers.keys())}")
    
    async def get_provider(self, asset: str) -> Optional[str]:
        """
        Get the best available provider for an asset.
        
        Returns the first healthy provider (by priority), excluding those
        in cooldown from rate limiting.
        """
        if not self._providers:
            await self.initialize()
        
        # Try each provider in priority order
        for name in DEFAULT_PROVIDERS:
            if name not in self._providers:
                continue
            
            provider = self._providers[name]
            if provider.is_available():
                return name
        
        # If all in cooldown, return the one with shortest wait
        best = None
        best_time = None
        
        for name, provider in self._providers.items():
            if not provider.is_active:
                continue
            
            if provider.cooldown_until:
                if best_time is None or provider.cooldown_until < best_time:
                    best = name
                    best_time = provider.cooldown_until
        
        return best or "yfinance"  # Fallback to yfinance
    
    async def report_success(self, provider_name: str) -> None:
        """Report a successful API call."""
        if provider_name not in self._providers:
            return
        
        provider = self._providers[provider_name]
        provider.success_count += 1
        provider.last_checked = datetime.utcnow()
        provider.last_error = None
        
        # Mark healthy if had failures before
        if not provider.is_healthy and provider.fail_count == 0:
            provider.is_healthy = True
        
        # Save to Redis
        await self._save_provider_state(provider_name)
        
        logger.debug(f"[provider_registry] {provider_name} success")
    
    async def report_failure(
        self,
        provider_name: str,
        error: str = "unknown",
        error_code: Optional[int] = None
    ) -> None:
        """Report a failed API call."""
        if provider_name not in self._providers:
            return
        
        provider = self._providers[provider_name]
        provider.fail_count += 1
        provider.last_checked = datetime.utcnow()
        provider.last_error = error
        
        # Handle rate limiting (429)
        if error_code == 429 or "rate_limit" in error.lower() or "429" in str(error):
            provider.cooldown_until = datetime.utcnow() + timedelta(
                seconds=self._cooldown_seconds)
            provider.is_healthy = False
            
            logger.warning(
                f"[provider_registry] {provider_name} rate limited, cooling down for "
                f"{self._cooldown_seconds}s")
            
            # Alert admins
            await self._alert_admins(provider_name, "rate_limited")
        
        # Too many failures = unhealthy
        if provider.fail_count >= 10:
            fail_rate = provider.fail_count / (
                provider.fail_count + provider.success_count)
            if fail_rate > 0.5:
                provider.is_healthy = False
        
        # Save to Redis
        await self._save_provider_state(provider_name)
        
        logger.debug(f"[provider_registry] {provider_name} failure: {error}")
    
    async def _save_provider_state(self, provider_name: str) -> None:
        """Save provider state to Redis."""
        if not self._redis or provider_name not in self._providers:
            return
        
        try:
            import json
            provider = self._providers[provider_name]
            self._redis.hset(
                "provider_health",
                provider_name,
                json.dumps(provider.to_dict())
            )
        except Exception:
            pass
    
    async def _alert_admins(self, provider_name: str, alert_type: str) -> None:
        """Send alert to admins about provider issues."""
        try:
            from config import ADMIN_IDS
            import os
            
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not bot_token:
                return
            
            import requests
            message = f"🚨 Provider Alert: {provider_name} - {alert_type}"
            
            for admin_id in (ADMIN_IDS or []):
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": admin_id, "text": message},
                        timeout=10,
                    )
                except Exception:
                    pass
        except Exception:
            pass
    
    def get_health(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """Get health status for a provider."""
        if provider_name in self._providers:
            return self._providers[provider_name].to_dict()
        return None
    
    def get_all_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all providers."""
        return {
            name: provider.to_dict()
            for name, provider in self._providers.items()
        }
    
    def get_unhealthy(self) -> List[tuple[str, int]]:
        """Get list of unhealthy providers with their fail durations."""
        unhealthy = []
        
        now = datetime.utcnow()
        for name, provider in self._providers.items():
            if not provider.is_healthy:
                # Estimate fail duration
                if provider.last_checked:
                    duration = (now - provider.last_checked).total_seconds() / 60
                else:
                    duration = 0
                unhealthy.append((name, duration))
        
        return unhealthy


# Global provider registry
_provider_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    """Get or create the global provider registry."""
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = ProviderRegistry()
    return _provider_registry


# Convenience functions

async def get_provider_for_asset(asset: str) -> str:
    """Get the best provider for an asset."""
    registry = get_provider_registry()
    return await registry.get_provider(asset)


async def report_provider_success(provider: str) -> None:
    """Report a successful provider call."""
    registry = get_provider_registry()
    await registry.report_success(provider)


async def report_provider_failure(
    provider: str,
    error: str = "unknown",
    error_code: Optional[int] = None
) -> None:
    """Report a failed provider call."""
    registry = get_provider_registry()
    await registry.report_failure(provider, error, error_code)
