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


def _runtime_provider_rows_from_universe(
    universe: dict[str, list[str]] | None,
    *,
    source_lookup,
) -> dict[str, list[dict[str, Any]]]:
    """Convert provider-verified runtime discovery into registry rows.

    The engine's runtime discovery already covers crypto, FX, equities, indices
    and commodities.  This adapter mirrors only provider-backed symbols into the
    durable instrument catalogue so the website and API expose the same market
    universe.  Manual/static-only symbols are deliberately excluded.
    """
    class_aliases = {
        "crypto": "crypto",
        "fx": "forex",
        "forex": "forex",
        "stocks": "equity",
        "stock": "equity",
        "equities": "equity",
        "equity": "equity",
        "indices": "index",
        "index": "index",
        "commodities": "commodity",
        "commodity": "commodity",
    }
    ignored_sources = {"", "unknown", "manual_config", "static_fallback"}
    rows_by_provider: dict[str, list[dict[str, Any]]] = {}

    def identity(symbol: str, asset_class: str) -> tuple[str, str, str]:
        sym = str(symbol or "").upper().strip().replace("/", "").replace("-", "").replace("_", "")
        if asset_class == "crypto":
            for suffix in ("USDT", "USDC", "BUSD", "USD"):
                if sym.endswith(suffix) and len(sym) > len(suffix):
                    return sym[: -len(suffix)], suffix, "spot"
            return sym, "USD", "spot"
        if asset_class == "forex" and len(sym) >= 6:
            return sym[:3], sym[3:6], "cfd"
        if asset_class == "equity":
            return sym, "USD", "cash_equity"
        if asset_class == "index":
            return sym, "USD", "cfd"
        if asset_class == "commodity":
            if len(sym) == 6 and sym.endswith("USD"):
                return sym[:3], "USD", "cfd"
            return sym, "USD", "cfd"
        return sym, "USD", "spot"

    for raw_class, symbols in dict(universe or {}).items():
        asset_class = class_aliases.get(str(raw_class or "").strip().lower())
        if not asset_class:
            continue
        for raw_symbol in symbols or []:
            symbol = str(raw_symbol or "").upper().strip()
            if not symbol:
                continue
            try:
                sources = tuple(source_lookup(symbol) or ())
            except Exception:
                sources = ()
            trusted_sources = [
                str(source or "").strip().lower()
                for source in sources
                if str(source or "").strip().lower() not in ignored_sources
            ]
            if not trusted_sources:
                continue
            base, quote, instrument_type = identity(symbol, asset_class)
            if not base or not quote or base == quote:
                continue
            for provider in dict.fromkeys(trusted_sources):
                row = {
                    "provider": provider,
                    "venue": provider,
                    "provider_symbol": symbol,
                    "provider_instrument_id": symbol,
                    "asset_class": asset_class,
                    "instrument_type": instrument_type,
                    "base": base,
                    "quote": quote,
                    "settlement": quote,
                    "market_status": "active",
                    "tradable": True,
                    "capabilities": ["historical_ohlc", "live_quotes"],
                    "metadata": {
                        "source": "runtime_pair_discovery",
                        "runtime_asset_class": str(raw_class),
                    },
                }
                rows_by_provider.setdefault(provider, []).append(row)

    # Deduplicate provider/symbol pairs without disturbing discovery order.
    for provider, rows in list(rows_by_provider.items()):
        seen: set[tuple[str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            key = (provider, str(row.get("provider_symbol") or ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        rows_by_provider[provider] = deduped
    return rows_by_provider


async def refresh_instrument_catalogue_once() -> dict[str, Any]:
    """Discover provider metadata outside the DB transaction, then persist it."""
    from data.connectors.coingecko_adapter import discover_instruments as coingecko_discover
    from data.connectors.defillama_adapter import discover_instruments as defillama_discover
    from data.instrument_discovery import DynamicInstrumentRegistry
    from data.pair_discovery import asset_discovery_sources, get_all_tradable_assets
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

    # Mirror the same provider-backed multi-asset universe used by the engine
    # into the durable catalogue consumed by Market Explorer.  This closes the
    # historical crypto-only catalogue gap without admitting static fallbacks.
    runtime_top = max(
        10,
        int(os.getenv("INSTRUMENT_RUNTIME_DISCOVERY_TOP", "40") or 40),
    )
    try:
        runtime_universe = await asyncio.wait_for(
            asyncio.to_thread(
                get_all_tradable_assets,
                crypto_limit=runtime_top,
                stock_limit=runtime_top,
            ),
            timeout=max(provider_timeout * 3.0, 30.0),
        )
        runtime_rows = _runtime_provider_rows_from_universe(
            runtime_universe,
            source_lookup=asset_discovery_sources,
        )
        for provider, rows in runtime_rows.items():
            if not rows:
                continue
            provider_rows.setdefault(provider, []).extend(rows)
            result = registry.ingest(provider, rows).to_dict()
            previous = provider_results.get(provider)
            if isinstance(previous, dict) and previous.get("state") == "ok":
                result["discovered"] = int(previous.get("discovered") or 0) + int(result.get("discovered") or 0)
                result["created"] = int(previous.get("created") or 0) + int(result.get("created") or 0)
                result["updated"] = int(previous.get("updated") or 0) + int(result.get("updated") or 0)
                result["unchanged"] = int(previous.get("unchanged") or 0) + int(result.get("unchanged") or 0)
            provider_results[provider] = result
        provider_results["runtime_multiasset"] = {
            "provider": "runtime_multiasset",
            "state": "ok",
            "reason": None,
            "discovered": sum(len(values) for values in runtime_rows.values()),
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "mapping_failures": 0,
            "duration_ms": 0.0,
            "asset_classes": {
                str(key): len(value or [])
                for key, value in dict(runtime_universe or {}).items()
            },
        }
    except Exception as exc:
        provider_results["runtime_multiasset"] = {
            "provider": "runtime_multiasset",
            "state": "failed",
            "reason": f"{type(exc).__name__}:{str(exc)[:160]}",
            "discovered": 0,
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "mapping_failures": 0,
            "duration_ms": 0.0,
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
