"""Short-lived DB reads for the provider-discovered engine universe."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_database_universe(
    session: AsyncSession,
    *,
    asset_classes: Iterable[str] | None = None,
    limit: int = 200,
) -> list[str]:
    """Load certified instruments with bound parameters only.

    The query deliberately avoids driver-specific array casts so it behaves
    consistently with asyncpg, psycopg and test databases.
    """
    aliases = {
        "fx": "forex",
        "stock": "equity",
        "stocks": "equity",
        "indices": "index",
        "futures": "future",
    }
    wanted = sorted({
        aliases.get(str(x).strip().lower(), str(x).strip().lower())
        for x in (asset_classes or ())
        if str(x).strip()
    })
    params: dict[str, object] = {"limit": max(1, min(int(limit), 2000))}
    class_clause = ""
    if wanted:
        placeholders: list[str] = []
        for index, asset_class in enumerate(wanted):
            key = f"asset_class_{index}"
            placeholders.append(f":{key}")
            params[key] = asset_class
        class_clause = " AND LOWER(i.asset_class) IN (" + ",".join(placeholders) + ")"
    statement = text("""
        SELECT DISTINCT i.canonical_symbol
        FROM instruments i
        JOIN provider_instruments pi
          ON pi.canonical_instrument_id = i.instrument_id
        LEFT JOIN instrument_certifications ic
          ON ic.instrument_id = i.instrument_id
        WHERE i.active = TRUE
          AND i.tradable = TRUE
          AND pi.data_enabled = TRUE
          AND pi.market_status IN ('active','open','trading')
          AND i.discovery_status IN (
            'metadata_validated','historical_data_ready','live_quote_ready',
            'analysis_ready','shadow','paper_certified','delivery_certified',
            'testnet_certified','live_guarded'
          )
    """ + class_clause + " ORDER BY i.canonical_symbol LIMIT :limit")
    result = await session.execute(statement, params)
    return [str(row[0]).upper() for row in result.all() if row and row[0]]
