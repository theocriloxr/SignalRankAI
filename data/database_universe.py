"""Short-lived DB reads for the provider-discovered engine universe."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_database_universe(
    session: AsyncSession,
    *,
    asset_classes: Iterable[str] | None = None,
    limit: int | None = None,
    page_size: int = 250,
) -> list[str]:
    """Load certified instruments with bound parameters only.

    Read the complete eligible catalogue using bounded keyset pages by default.
    A caller may explicitly request a smaller result with ``limit``. The engine
    must see every symbol before its fair scan scheduler applies a work budget.
    No network I/O or execution authorization is performed here.
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
    statement = text(
        """
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
          AND i.canonical_symbol > :after_symbol
          AND i.discovery_status IN (
            'metadata_validated','historical_data_ready','live_quote_ready',
            'analysis_ready','shadow','paper_certified','delivery_certified',
            'testnet_certified','live_guarded'
          )
    """
        + class_clause
        + " ORDER BY i.canonical_symbol LIMIT :limit"
    )
    symbols: list[str] = []
    while remaining is None or remaining > 0:
        params["limit"] = min(batch_size, remaining) if remaining is not None else batch_size
        result = await session.execute(statement, params)
        page = [str(row[0]) for row in result.all() if row and row[0]]
        if not page:
            break
        symbols.extend(symbol.upper() for symbol in page)
        params["after_symbol"] = page[-1]
        if remaining is not None:
            remaining -= len(page)
        if len(page) < params["limit"]:
            break
    return symbols
