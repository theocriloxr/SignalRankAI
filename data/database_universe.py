"""Short-lived DB reads for the provider-discovered engine universe."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_database_universe(
    session: AsyncSession,
    *,
    asset_classes: Iterable[str] | None = None,
    limit: int | None = None,
    page_size: int = 250,
    require_analysis_ready: bool = False,
    now: datetime | None = None,
) -> list[str]:
    """Load registry candidates with bound parameters only.

    Read the complete eligible catalogue using bounded keyset pages by default.
    A caller may explicitly request a smaller result with ``limit``. The engine
    must see every symbol before its fair scan scheduler applies a work budget.
    No network I/O or execution authorization is performed here.

    The focused staging scanner additionally requires an analysis-ready record,
    candle/quote capabilities, and metadata refreshed within 15 minutes. These
    are necessary registry checks, not proof of fresh candles, entitlement or
    broker authorization. Metadata-only discovery never satisfies this path.
    """
    aliases = {
        "fx": "forex",
        "stock": "equity",
        "stocks": "equity",
        "indices": "index",
        "futures": "future",
    }
    wanted = sorted(
        {aliases.get(str(x).strip().lower(), str(x).strip().lower()) for x in (asset_classes or ()) if str(x).strip()}
    )
    remaining = max(1, int(limit)) if limit is not None else None
    batch_size = max(1, min(int(page_size), 2000))
    params: dict[str, object] = {"after_symbol": ""}
    class_clause = ""
    if wanted:
        placeholders: list[str] = []
        for index, asset_class in enumerate(wanted):
            key = f"asset_class_{index}"
            placeholders.append(f":{key}")
            params[key] = asset_class
        class_clause = " AND LOWER(i.asset_class) IN (" + ",".join(placeholders) + ")"
    if type(require_analysis_ready) is not bool:
        raise ValueError("analysis_readiness_must_be_boolean")
    readiness_clause = ""
    selected_columns = "i.canonical_symbol"
    group_clause = ""
    if require_analysis_ready:
        checked_at = now if now is not None else datetime.now(timezone.utc)
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("registry_clock_requires_timezone")
        # These database columns are UTC TIMESTAMP WITHOUT TIME ZONE.
        params["registry_now"] = checked_at.astimezone(timezone.utc).replace(tzinfo=None)
        params["registry_cutoff"] = params["registry_now"] - timedelta(minutes=15)
        readiness_clause = """
          AND i.discovery_status IN (
            'analysis_ready','shadow','paper_certified','delivery_certified',
            'testnet_certified','live_guarded'
          )
          AND ic.readiness_state IN (
            'analysis_ready','shadow','paper_certified','delivery_certified',
            'testnet_certified','live_guarded'
          )
          AND i.last_verified_at BETWEEN :registry_cutoff AND :registry_now
          AND ic.certified_at BETWEEN :registry_cutoff AND :registry_now
          AND pi.last_successful_refresh_at BETWEEN :registry_cutoff AND :registry_now
          AND pi.historical_candles_supported = TRUE
          AND pi.live_quotes_supported = TRUE
          AND pi.delisted_at IS NULL
          AND TRIM(pi.provider) <> '' AND TRIM(pi.provider_symbol) <> ''
          AND ic.evidence IS NOT NULL
        """
        selected_columns += ", MIN(LOWER(i.asset_class))"
        group_clause = " GROUP BY i.canonical_symbol HAVING COUNT(DISTINCT LOWER(i.asset_class)) = 1"
    statement = text(
        """
        SELECT DISTINCT """ + selected_columns + """
        FROM instruments i
        JOIN provider_instruments pi
          ON pi.canonical_instrument_id = i.instrument_id
        LEFT JOIN instrument_certifications ic
          ON ic.instrument_id = i.instrument_id
        WHERE i.active = TRUE
          AND i.tradable = TRUE
          AND pi.data_enabled = TRUE
          AND pi.market_status IN ('active','open','trading')
          AND i.canonical_symbol > :after_symbol
          AND i.discovery_status IN (
            'metadata_validated','historical_data_ready','live_quote_ready',
            'analysis_ready','shadow','paper_certified','delivery_certified',
            'testnet_certified','live_guarded'
          )
    """
        + class_clause + readiness_clause + group_clause
        + " ORDER BY i.canonical_symbol LIMIT :limit"
    )
    symbols: list[str] = []
    while remaining is None or remaining > 0:
        params["limit"] = min(batch_size, remaining) if remaining is not None else batch_size
        result = await session.execute(statement, params)
        rows = result.all()
        page = [str(row[0]) for row in rows if row and row[0]]
        if not page:
            break
        if require_analysis_ready:
            from core.asset_registry import resolve_asset_spec

            for row in rows:
                spec = resolve_asset_spec(str(row[0]))
                actual = aliases.get(spec.asset_class, spec.asset_class)
                if spec.actionable and not spec.analysis_only and actual == aliases.get(row[1], row[1]):
                    symbols.append(str(row[0]).upper())
        else:
            symbols.extend(symbol.upper() for symbol in page)
        params["after_symbol"] = page[-1]
        if remaining is not None:
            remaining -= len(page)
        if len(page) < params["limit"]:
            break
    return symbols
