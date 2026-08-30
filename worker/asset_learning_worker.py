"""Bounded all-asset candle collector for analytics/ML learning.

This role never creates or delivers signals.  It samples the configured asset
universe, fetches only analysis timeframes, and writes normalized candles to
MarketCandle after all network calls have completed.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

def _env_bool(name: str, default: bool = False) -> bool:
    raw=os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1","true","yes","on"}

def _to_ms(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        n=int(value); return n*1000 if n < 1_000_000_000_000 else n
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()*1000)
    except Exception:
        return None

class AssetLearningWorker:
    def __init__(self) -> None:
        self.interval=max(60, int(os.getenv("ASSET_LEARNING_INTERVAL_SECONDS", "900") or 900))
        self.batch_size=max(1, min(50, int(os.getenv("ASSET_LEARNING_ASSETS_PER_CYCLE", "12") or 12)))
        self.concurrency=max(1, min(4, int(os.getenv("ASSET_LEARNING_CONCURRENCY", "2") or 2)))
        self.timeframes=tuple(x.strip() for x in os.getenv("ASSET_LEARNING_TIMEFRAMES", "1h,4h,1d").split(",") if x.strip())
        self._cursor=0

    def _universe(self) -> list[str]:
        from data.pair_discovery import get_all_tradable_assets
        raw=get_all_tradable_assets(crypto_limit=int(os.getenv("ASSET_LEARNING_CRYPTO_LIMIT", "40")), stock_limit=int(os.getenv("ASSET_LEARNING_STOCK_LIMIT", "40"))) or {}
        ordered=[]
        for key in ("crypto","fx","stocks","indices","commodities"):
            for asset in raw.get(key, []) or []:
                sym=str(asset).upper().strip()
                if sym and sym not in ordered: ordered.append(sym)
        return ordered

    async def run_once(self) -> dict[str,int]:
        universe=self._universe()
        if not universe: return {"assets":0,"candles":0}
        start=self._cursor % len(universe)
        assets=(universe+universe)[start:start+self.batch_size]
        self._cursor=(start+len(assets)) % len(universe)
        sem=asyncio.Semaphore(self.concurrency)
        from data.market_data import fetch_market_data_cached
        async def fetch(asset: str):
            async with sem:
                try: return asset, await fetch_market_data_cached(
                        asset, self.timeframes, diagnostic_scope="analysis"
                    )
                except Exception as exc:
                    logger.info("[asset_learning] fetch_failed asset=%s err=%s", asset, exc); return asset, {}
        fetched=await asyncio.gather(*(fetch(a) for a in assets))
        rows=[]
        for asset,data in fetched:
            for tf,payload in (data or {}).items():
                if tf.startswith("_") or not isinstance(payload,dict): continue
                for candle in payload.get("candles") or []:
                    ts=_to_ms(candle.get("timestamp") or candle.get("time"))
                    if ts is None: continue
                    try:
                        rows.append((asset,tf,ts,float(candle["open"]),float(candle["high"]),float(candle["low"]),float(candle["close"]),float(candle.get("volume") or 0.0)))
                    except Exception: continue
        if not rows: return {"assets":len(assets),"candles":0}
        from db.market_cache import upsert_market_candle
        from db.priority import DBPriority
        from db.session import NoncriticalWriteDropped, get_session
        try:
            async with get_session(priority=DBPriority.BACKGROUND,label="asset_learning_candle_write") as session:
                for asset,tf,ts,o,h,l,c,v in rows:
                    await upsert_market_candle(session,symbol=asset,timeframe=tf,open_time_ms=ts,open=o,high=h,low=l,close=c,volume=v,is_final=True)
                await session.commit()
            logger.info("[asset_learning] assets=%s candles=%s timeframes=%s",len(assets),len(rows),self.timeframes)
            return {"assets":len(assets),"candles":len(rows)}
        except NoncriticalWriteDropped:
            logger.info("[asset_learning] deferred reason=db_background_capacity")
            return {"assets":len(assets),"candles":0}

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            if _env_bool("ASSET_LEARNING_ENABLED", True):
                try: await self.run_once()
                except asyncio.CancelledError: raise
                except Exception as exc: logger.error("[asset_learning] cycle_failed err=%s",exc,exc_info=True)
            try: await asyncio.wait_for(stop_event.wait(),timeout=self.interval)
            except asyncio.TimeoutError: pass

asset_learning_worker=AssetLearningWorker()
