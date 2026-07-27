"""Lazy, capability-aware provider health registry.

This compatibility service no longer opens a network connection at import or
construction time.  It persists health through an injected/optional async Redis
client and never invents a fallback provider when every compatible provider is
unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import inspect
import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from data.provider_catalog import ProviderSpec, list_provider_specs, providers_for_asset_class
from services.asset_mapper import classify_asset
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)
DEFAULT_COOLDOWN_SECONDS = 60

AlertCallback = Callable[[str, str], Awaitable[None] | None]


def _normalise_asset_class(value: str) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "crypto": "crypto_spot",
        "fx": "forex",
        "stock": "equity",
        "stocks": "equity",
        "commodity": "commodity_spot",
        "indices": "index",
    }
    return aliases.get(raw, raw)


@dataclass(slots=True)
class ProviderHealth:
    name: str
    is_active: bool = True
    is_healthy: bool = True
    fail_count: int = 0
    success_count: int = 0
    consecutive_failures: int = 0
    last_checked: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    last_failure_category: Optional[str] = None
    cooldown_until: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_available(self, now: datetime | None = None) -> bool:
        now = now or now_utc_naive()
        return bool(
            self.is_active
            and self.is_healthy
            and (self.cooldown_until is None or now >= self.cooldown_until)
        )

    def get_success_rate(self) -> float | None:
        total = self.success_count + self.fail_count
        return None if total == 0 else (self.success_count / total) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "is_active": self.is_active,
            "is_healthy": self.is_healthy,
            "is_available": self.is_available(),
            "fail_count": self.fail_count,
            "success_count": self.success_count,
            "consecutive_failures": self.consecutive_failures,
            "success_rate": self.get_success_rate(),
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error,
            "last_failure_category": self.last_failure_category,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "ProviderHealth":
        def _dt(key: str) -> datetime | None:
            value = data.get(key)
            if not value:
                return None
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                return None

        return cls(
            name=name,
            is_active=bool(data.get("is_active", True)),
            is_healthy=bool(data.get("is_healthy", True)),
            fail_count=max(0, int(data.get("fail_count", 0) or 0)),
            success_count=max(0, int(data.get("success_count", 0) or 0)),
            consecutive_failures=max(0, int(data.get("consecutive_failures", 0) or 0)),
            last_checked=_dt("last_checked"),
            last_success=_dt("last_success"),
            last_error=data.get("last_error"),
            last_failure_category=data.get("last_failure_category"),
            cooldown_until=_dt("cooldown_until"),
            metadata=dict(data.get("metadata") or {}),
        )


class ProviderRegistry:
    """Capability-aware provider health and cooldown registry.

    Redis is optional and lazily connected.  ``get_provider`` returns ``None``
    when no compatible provider is healthy; callers must then defer/fail closed
    rather than silently routing to yfinance or another incompatible source.
    """

    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        alert_callback: AlertCallback | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        self._providers: Dict[str, ProviderHealth] = {}
        self._redis = redis_client
        self._redis_attempted = redis_client is not None
        self._redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL") or None
        self._alert_callback = alert_callback
        self._cooldown_seconds = max(
            1,
            int(cooldown_seconds or os.getenv("PROVIDER_COOLDOWN_SECONDS", DEFAULT_COOLDOWN_SECONDS)),
        )
        self._failure_threshold = max(1, int(os.getenv("PROVIDER_FAILURE_THRESHOLD", "5")))
        self._redis_hash = os.getenv("PROVIDER_HEALTH_REDIS_HASH", "signalrank:provider_health")

    async def _ensure_redis(self) -> Any | None:
        if self._redis_attempted:
            return self._redis
        self._redis_attempted = True
        if not self._redis_url:
            return None
        try:
            from redis.asyncio import Redis

            client = Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                max_connections=max(1, int(os.getenv("REDIS_MAX_CONNECTIONS", "24"))),
            )
            await client.ping()
            self._redis = client
        except Exception as exc:
            logger.debug("provider health Redis unavailable: %s", exc)
            self._redis = None
        return self._redis

    async def initialize(self, providers: Optional[Iterable[str]] = None) -> None:
        keys = list(providers or [spec.key for spec in list_provider_specs(implemented_only=True)])
        for key in keys:
            self._providers.setdefault(key, ProviderHealth(key))

        redis_client = await self._ensure_redis()
        if redis_client is not None:
            try:
                values = await redis_client.hmget(self._redis_hash, keys)
                for key, raw in zip(keys, values):
                    if raw:
                        self._providers[key] = ProviderHealth.from_dict(key, json.loads(raw))
            except Exception as exc:
                logger.debug("provider health state restore failed: %s", exc)

    def _compatible_specs(self, asset: str, asset_class: str | None = None) -> tuple[ProviderSpec, ...]:
        classified = _normalise_asset_class(asset_class or classify_asset(asset))
        specs = providers_for_asset_class(classified, enabled_only=True)
        # Compatibility with old generic categories returned by classify_asset.
        if not specs and classified == "commodity":
            specs = providers_for_asset_class("commodity_spot", enabled_only=True)
        return specs

    async def get_provider(self, asset: str, asset_class: str | None = None) -> Optional[str]:
        if not self._providers:
            await self.initialize()
        for spec in self._compatible_specs(asset, asset_class):
            health = self._providers.get(spec.key)
            if health is None:
                continue
            if spec.configured() and health.is_available():
                return spec.key
        return None

    async def report_success(self, provider_name: str) -> None:
        provider = self._providers.setdefault(provider_name, ProviderHealth(provider_name))
        now = now_utc_naive()
        provider.success_count += 1
        provider.consecutive_failures = 0
        provider.last_checked = now
        provider.last_success = now
        provider.last_error = None
        provider.last_failure_category = None
        provider.cooldown_until = None
        provider.is_healthy = True
        await self._save_provider_state(provider_name)

    async def report_failure(
        self,
        provider_name: str,
        error: str = "unknown",
        error_code: Optional[int] = None,
        *,
        category: str | None = None,
    ) -> None:
        provider = self._providers.setdefault(provider_name, ProviderHealth(provider_name))
        provider.fail_count += 1
        provider.consecutive_failures += 1
        provider.last_checked = now_utc_naive()
        provider.last_error = str(error)[:500]
        text = str(error).lower()
        failure_category = category or (
            "rate_limit" if error_code == 429 or "429" in text or "rate_limit" in text else "provider_error"
        )
        provider.last_failure_category = failure_category

        if failure_category == "rate_limit" or provider.consecutive_failures >= self._failure_threshold:
            multiplier = min(8, max(1, provider.consecutive_failures - self._failure_threshold + 1))
            provider.cooldown_until = now_utc_naive() + timedelta(seconds=self._cooldown_seconds * multiplier)
            provider.is_healthy = False
            await self._alert(provider_name, failure_category)

        await self._save_provider_state(provider_name)

    async def _save_provider_state(self, provider_name: str) -> None:
        redis_client = await self._ensure_redis()
        if redis_client is None:
            return
        try:
            await redis_client.hset(
                self._redis_hash,
                provider_name,
                json.dumps(self._providers[provider_name].to_dict(), sort_keys=True),
            )
        except Exception as exc:
            logger.debug("provider health persistence failed: %s", exc)

    async def _alert(self, provider_name: str, alert_type: str) -> None:
        if self._alert_callback is None:
            logger.warning("provider %s entered %s", provider_name, alert_type)
            return
        try:
            result = self._alert_callback(provider_name, alert_type)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.warning("provider alert callback failed: %s", exc)

    def get_health(self, provider_name: str) -> Optional[Dict[str, Any]]:
        provider = self._providers.get(provider_name)
        return provider.to_dict() if provider else None

    def get_all_health(self) -> Dict[str, Dict[str, Any]]:
        return {name: provider.to_dict() for name, provider in self._providers.items()}

    def get_unhealthy(self) -> List[tuple[str, int]]:
        now = now_utc_naive()
        result: List[tuple[str, int]] = []
        for name, provider in self._providers.items():
            if provider.is_available(now):
                continue
            duration = int((now - provider.last_checked).total_seconds() / 60) if provider.last_checked else 0
            result.append((name, max(0, duration)))
        return result


_provider_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = ProviderRegistry()
    return _provider_registry


async def get_provider_for_asset(asset: str, asset_class: str | None = None) -> Optional[str]:
    return await get_provider_registry().get_provider(asset, asset_class)


async def report_provider_success(provider: str) -> None:
    await get_provider_registry().report_success(provider)


async def report_provider_failure(
    provider: str,
    error: str = "unknown",
    error_code: Optional[int] = None,
) -> None:
    await get_provider_registry().report_failure(provider, error, error_code)
