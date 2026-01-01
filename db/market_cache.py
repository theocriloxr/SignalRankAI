from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MarketCandle, MarketTick


async def upsert_market_tick(
    session: AsyncSession,
    *,
    symbol: str,
    price: float,
    event_time_ms: Optional[int] = None,
) -> None:
    sym = str(symbol or "").upper().strip()[:32]
    if not sym:
        return

    stmt = insert(MarketTick).values(
        symbol=sym,
        price=float(price),
        event_time_ms=int(event_time_ms) if event_time_ms is not None else None,
        updated_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[MarketTick.symbol],
        set_={
            "price": stmt.excluded.price,
            "event_time_ms": stmt.excluded.event_time_ms,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)


async def upsert_market_candle(
    session: AsyncSession,
    *,
    symbol: str,
    timeframe: str,
    open_time_ms: int,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float = 0.0,
    close_time_ms: Optional[int] = None,
    is_final: bool = False,
) -> None:
    sym = str(symbol or "").upper().strip()[:32]
    tf = str(timeframe or "").lower().strip()[:8]
    if not sym or not tf:
        return

    stmt = insert(MarketCandle).values(
        symbol=sym,
        timeframe=tf,
        open_time_ms=int(open_time_ms),
        close_time_ms=int(close_time_ms) if close_time_ms is not None else None,
        open=float(open),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=float(volume or 0.0),
        is_final=bool(is_final),
        updated_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_market_candles_symbol_tf_open",
        set_={
            "close_time_ms": stmt.excluded.close_time_ms,
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "is_final": stmt.excluded.is_final,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)


async def get_recent_candles(
    session: AsyncSession,
    *,
    symbol: str,
    timeframe: str,
    limit: int = 200,
) -> list[dict]:
    sym = str(symbol or "").upper().strip()[:32]
    tf = str(timeframe or "").lower().strip()[:8]
    if not sym or not tf:
        return []

    q = (
        select(MarketCandle)
        .where(MarketCandle.symbol == sym)
        .where(MarketCandle.timeframe == tf)
        .order_by(MarketCandle.open_time_ms.desc())
        .limit(max(1, int(limit)))
    )
    res = await session.execute(q)
    rows = list(res.scalars().all())
    rows.reverse()

    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "timestamp": int(r.open_time_ms),
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume or 0.0),
            }
        )
    return out


async def prune_old_candles(
    session: AsyncSession,
    *,
    symbol: str,
    timeframe: str,
    keep_last: int = 500,
) -> None:
    # Lightweight pruning: keep only last N candles per (symbol, timeframe).
    sym = str(symbol or "").upper().strip()[:32]
    tf = str(timeframe or "").lower().strip()[:8]
    keep = max(1, int(keep_last))
    if not sym or not tf:
        return

    q = (
        select(MarketCandle.open_time_ms)
        .where(MarketCandle.symbol == sym)
        .where(MarketCandle.timeframe == tf)
        .order_by(MarketCandle.open_time_ms.desc())
        .offset(keep)
        .limit(1)
    )
    res = await session.execute(q)
    cutoff = res.scalar_one_or_none()
    if cutoff is None:
        return

    await session.execute(
        MarketCandle.__table__.delete()
        .where(MarketCandle.symbol == sym)
        .where(MarketCandle.timeframe == tf)
        .where(MarketCandle.open_time_ms <= int(cutoff))
    )
