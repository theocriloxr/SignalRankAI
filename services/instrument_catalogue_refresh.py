"""Provider instrument catalogue refresh owned by analytics in decomposed deployments."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from db.session import get_session, is_db_configured

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default)) or default))
    except (TypeError, ValueError):
        return max(minimum, float(default))


def _db_priority() -> str:
    role = str(os.getenv("DB_ROLE") or os.getenv("RUN_MODE") or "").strip().lower()
    return "analytics" if role == "analytics" or role.startswith("analytics-") else "background"


async def refresh_instrument_catalogue_once() -> dict[str, Any]:
    """Discover provider metadata outside the DB transaction, then persist it."""
    from data.connectors.coingecko_adapter import discover_instruments as coingecko_discover
    from data.connectors.defillama_adapter import discover_instruments as defillama_discover
    from data.instrument_discovery import DynamicInstrumentRegistry
    from db.ecosystem_bootstrap import persist_instrument_registry, record_discovery_run

    top = max(10, int(os.getenv("INSTRUMENT_DISCOVERY_TOP", "150") or 150))
    provider_timeout = max(
        5.0,
        _env_float("INSTRUMENT_DISCOVERY_PROVIDER_TIMEOUT_SECONDS", 20.0, minimum=5.0),
    )
    providers = {
        "coingecko": coingecko_discover,
        "defillama": defillama_discover,
    }
    provider_rows: dict[str, list[dict]] = {}
    provider_results: dict[str, dict] = {}
    registry = DynamicInstrumentRegistry()

    for provider, discover in providers.items():
        try:
            rows = await asyncio.wait_for(
                asyncio.to_thread(discover, top=top),
                timeout=provider_timeout,
            )
            payload = list(rows or [])
            provider_rows[provider] = payload
            provider_results[provider] = registry.ingest(provider, payload).to_dict()
        except Exception as exc:
            provider_results[provider] = {
                "provider": provider,
                "state": "failed",
                "reason": f"{type(exc).__name__}:{str(exc)[:160]}",
            }

    if not is_db_configured():
        return {
            "ok": False,
            "reason": "database_not_configured",
            "providers": provider_results,
        }

    timeout_seconds = max(
        30.0,
        _env_float("INSTRUMENT_DISCOVERY_DB_TIMEOUT_SECONDS", 180.0, minimum=30.0),
    )
    async with get_session(
        priority=_db_priority(),
        label="analytics.instrument_discovery.persist",
        timeout_seconds=timeout_seconds,
        drop_if_busy=False,
    ) as session:
        persisted = await persist_instrument_registry(
            session,
            registry,
            provider_rows=provider_rows,
        )
        for provider, result in provider_results.items():
            await record_discovery_run(session, provider, result)
        await session.commit()

    result = {
        "ok": True,
        "providers": provider_results,
        "persisted": persisted,
    }
    logger.info("[instrument_discovery] analytics refresh result=%s", result)
    return result


async def instrument_catalogue_refresh_loop(stop_event: asyncio.Event) -> None:
    interval = max(
        300.0,
        _env_float("DYNAMIC_UNIVERSE_REFRESH_SECONDS", 900.0, minimum=300.0),
    )
    initial_delay = max(
        0.0,
        _env_float("INSTRUMENT_DISCOVERY_STARTUP_DELAY_SECONDS", 45.0, minimum=0.0),
    )
    if initial_delay:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=initial_delay)
            return
        except asyncio.TimeoutError:
            pass

    while not stop_event.is_set():
        try:
            await refresh_instrument_catalogue_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "[instrument_discovery] analytics refresh failed error=%s",
                type(exc).__name__,
                exc_info=True,
            )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


__all__ = ["refresh_instrument_catalogue_once", "instrument_catalogue_refresh_loop"]
