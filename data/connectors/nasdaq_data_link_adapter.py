"""Nasdaq Data Link configured time-series adapter.

Because Nasdaq Data Link is dataset-oriented rather than a universal symbol
feed, the deployment must provide ``NASDAQ_DATA_LINK_DATASETS_JSON`` mapping
canonical symbols to dataset codes, for example ``{"GC": "CHRIS/CME_GC1"}``.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _dataset_map() -> dict[str, str]:
    raw = str(os.getenv("NASDAQ_DATA_LINK_DATASETS_JSON") or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except ValueError:
        return {}
    return {str(key).upper(): str(value) for key, value in payload.items()} if isinstance(payload, dict) else {}


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    if str(timeframe or "").lower() not in {"1d", "d", "day", "daily"}:
        return []
    api_key = str(os.getenv("NASDAQ_DATA_LINK_API_KEY") or "").strip()
    dataset = _dataset_map().get(str(symbol or "").upper().strip())
    if not api_key or not dataset or "/" not in dataset:
        return []
    database, code = dataset.split("/", 1)
    client = httpx_client.get_client("nasdaq_data_link")
    if client is None:
        return []
    params = {"api_key": api_key, "order": "asc", "limit": max(2, min(10000, int(limit or 200)))}
    try:
        response = await client.get(
            f"https://data.nasdaq.com/api/v3/datasets/{database}/{code}/data.json",
            params=params,
            timeout=min(15.0, max(1.0, float(timeout))),
        )
        if response.status_code != 200:
            return []
        payload = response.json() or {}
        dataset_data = payload.get("dataset_data") if isinstance(payload, dict) else None
        names = list(dataset_data.get("column_names") or []) if isinstance(dataset_data, dict) else []
        data = list(dataset_data.get("data") or []) if isinstance(dataset_data, dict) else []
        index = {str(name).lower(): pos for pos, name in enumerate(names)}
        required = {"date", "open", "high", "low", "close"}
        if not required.issubset(index):
            return []
        rows: List[Dict[str, Any]] = []
        for item in data:
            try:
                rows.append(
                    {
                        "timestamp": item[index["date"]],
                        "open": float(item[index["open"]]),
                        "high": float(item[index["high"]]),
                        "low": float(item[index["low"]]),
                        "close": float(item[index["close"]]),
                        "volume": float(item[index["volume"]]) if "volume" in index and item[index["volume"]] is not None else 0.0,
                    }
                )
            except (IndexError, TypeError, ValueError):
                continue
        return rows[-max(2, int(limit or 200)):]
    except Exception as exc:
        logger.debug("Nasdaq Data Link request failed: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
