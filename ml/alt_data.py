"""Alternative data features (owner-approved feature schema v5, 11 Nov 2026).

Three keyless public series, each used only from the moment it was published:

* ``fear_greed``: Crypto Fear & Greed index (alternative.me), daily at 00:00 UTC,
  scaled 0-1.
* ``hy_credit_spread``: ICE BofA US high-yield option-adjusted spread (FRED
  BAMLH0A0HYM2), in percent / 10; a value dated D is first used on D + 1 day.
* ``cot_net_position``: CFTC Commitments of Traders (legacy, futures only),
  non-commercial (speculative) net position / open interest for the asset's
  market. A report dated Tuesday T is released Friday afternoon US time and is
  first used from T + 3 days 21:30 UTC. An FX pair uses base minus quote (USD
  counts as 0), so EURUSD rises when speculators add euro longs.

Point-in-time use matters as much as the data: training fills each past row with
the value available *at that row's time* (``fill_frame``); live scoring reads
the same values from a cache the engine refreshes with its macro snapshot
(``refresh`` / ``live_values``), so a scan never waits on these hosts. A missing
or failed series is 0.0, like every other missing feature.
"""
from __future__ import annotations

import bisect
import csv
import io
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)

FEATURES = ("fear_greed", "hy_credit_spread", "cot_net_position")

FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
COT_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

# CFTC market name prefixes (legacy futures-only report).
COT_MARKETS = {
    "EUR": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
    "JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "CHF": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
    "CAD": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "AUD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "NZD": "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "XAU": "GOLD - COMMODITY EXCHANGE INC.",
    "XAG": "SILVER - COMMODITY EXCHANGE INC.",
    "WTI": "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
    "SPX": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
    "NDX": "NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE",
    "DJI": "DJIA x $5 - CHICAGO BOARD OF TRADE",
    "BTC": "BITCOIN - CHICAGO MERCANTILE EXCHANGE",
}
_FX = ("EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "USD")
_ASSET_TO_MARKET = {
    "XAUUSD": "XAU", "GOLD": "XAU", "XAGUSD": "XAG", "SILVER": "XAG",
    "WTI": "WTI", "USOIL": "WTI", "BRENT": "WTI", "UKOIL": "WTI",
    "US500": "SPX", "SPX500": "SPX", "NAS100": "NDX", "US100": "NDX", "US30": "DJI",
    "BTCUSDT": "BTC", "BTCUSD": "BTC",
}
_COT_RELEASE_LAG = timedelta(days=3, hours=21, minutes=30)
_FRED_LAG = timedelta(days=1)

_lock = threading.Lock()
_series: dict[str, tuple[list[float], list[float]]] = {}  # name -> (epoch seconds available, value)
_loaded_at: dict[str, float] = {}


def _enabled() -> bool:
    return str(os.getenv("ML_ALT_DATA_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _ttl() -> float:
    try:
        return max(600.0, float(os.getenv("ML_ALT_DATA_TTL_SECONDS", "21600") or 21600))
    except ValueError:
        return 21600.0


def _get(url: str, params: dict[str, Any] | None = None, timeout: float = 20.0) -> Any:
    import httpx

    response = httpx.get(url, params=params, timeout=timeout, headers={"User-Agent": "signalrank-ml/1.0"},
                         follow_redirects=True)
    response.raise_for_status()
    return response


def _store(name: str, points: Iterable[tuple[float, float]]) -> None:
    ordered = sorted((float(t), float(v)) for t, v in points)
    with _lock:
        _series[name] = ([t for t, _ in ordered], [v for _, v in ordered])
        _loaded_at[name] = time.time()


def _fresh(name: str) -> bool:
    return name in _series and time.time() - _loaded_at.get(name, 0.0) < _ttl()


def _load_fear_greed() -> None:
    rows = (_get(FNG_URL).json() or {}).get("data") or []
    _store("fear_greed", ((int(r["timestamp"]), float(r["value"]) / 100.0) for r in rows
                          if r.get("timestamp") and r.get("value") is not None))


def _load_hy_spread() -> None:
    text = _get(FRED_URL).text
    points = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2 or not row[0][:4].isdigit():
            continue
        try:
            day = datetime.strptime(row[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            points.append(((day + _FRED_LAG).timestamp(), float(row[1]) / 10.0))
        except ValueError:
            continue  # FRED writes "." for missing days
    _store("hy_credit_spread", points)


def _load_cot(code: str) -> None:
    market = COT_MARKETS[code]
    rows = _get(COT_URL, params={
        "$select": "report_date_as_yyyy_mm_dd,noncomm_positions_long_all,noncomm_positions_short_all,open_interest_all",
        "$where": f"market_and_exchange_names='{market}'",
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": "5000",
    }).json() or []
    points = []
    for r in rows:
        try:
            day = datetime.fromisoformat(str(r["report_date_as_yyyy_mm_dd"])[:10]).replace(tzinfo=timezone.utc)
            oi = float(r["open_interest_all"])
            if oi <= 0:
                continue
            net = (float(r["noncomm_positions_long_all"]) - float(r["noncomm_positions_short_all"])) / oi
            points.append(((day + _COT_RELEASE_LAG).timestamp(), net))
        except (KeyError, TypeError, ValueError):
            continue
    _store(f"cot:{code}", points)


def refresh(force: bool = False) -> dict[str, int]:
    """Load (or reload after the TTL) every series; returns points per series. Never raises."""
    if not _enabled():
        return {}
    loaders = [("fear_greed", _load_fear_greed), ("hy_credit_spread", _load_hy_spread)]
    loaders += [(f"cot:{code}", (lambda c=code: _load_cot(c))) for code in COT_MARKETS]
    out: dict[str, int] = {}
    for name, loader in loaders:
        if force or not _fresh(name):
            try:
                loader()
            except Exception as exc:
                logger.info("[alt_data] %s unavailable error=%s", name, type(exc).__name__)
                with _lock:
                    _loaded_at[name] = time.time() - _ttl() + 600.0  # retry in 10 minutes
        out[name] = len(_series.get(name, ([], []))[0])
    return out


def value_at(name: str, when: float) -> float:
    """Latest value published at or before ``when`` (epoch seconds); 0.0 when none."""
    times, values = _series.get(name, ([], []))
    index = bisect.bisect_right(times, float(when)) - 1
    return float(values[index]) if index >= 0 else 0.0


def cot_codes(asset: str) -> tuple[str | None, str | None]:
    """(base market, quote market) for an asset; None means 'not covered' (or USD)."""
    symbol = str(asset or "").upper().replace("/", "").replace("_", "")
    if symbol in _ASSET_TO_MARKET:
        return _ASSET_TO_MARKET[symbol], None
    if len(symbol) == 6 and symbol[:3] in _FX and symbol[3:] in _FX:
        base, quote = symbol[:3], symbol[3:]
        return (base if base != "USD" else None), (quote if quote != "USD" else None)
    return None, None


def cot_value(asset: str, when: float) -> float:
    base, quote = cot_codes(asset)
    value = value_at(f"cot:{base}", when) if base else 0.0
    if quote:
        value -= value_at(f"cot:{quote}", when)
    return round(value, 6)


def features_at(asset: str, when: float) -> dict[str, float]:
    return {
        "fear_greed": round(value_at("fear_greed", when), 6),
        "hy_credit_spread": round(value_at("hy_credit_spread", when), 6),
        "cot_net_position": cot_value(asset, when),
    }


def live_values(asset: str) -> dict[str, float]:
    """Current values from the cache only (no network): for live feature building."""
    return features_at(asset, time.time())


def fill_frame(frame: Any, *, time_column: str = "created_at", asset_column: str = "asset") -> Any:
    """Set the v5 columns on a training frame, point in time per row. Returns the frame."""
    import pandas as pd

    if not _enabled():
        for column in FEATURES:
            frame[column] = 0.0
        return frame
    refresh()
    stamps = pd.to_datetime(frame[time_column], errors="coerce", utc=True) if time_column in frame.columns else None
    assets = frame[asset_column].astype(str) if asset_column in frame.columns else None
    values = {column: [] for column in FEATURES}
    for index in range(len(frame)):
        stamp = stamps.iloc[index] if stamps is not None else None
        if stamp is None or pd.isna(stamp):
            for column in FEATURES:
                values[column].append(0.0)
            continue
        row = features_at(assets.iloc[index] if assets is not None else "", stamp.timestamp())
        for column in FEATURES:
            values[column].append(row[column])
    for column in FEATURES:
        frame[column] = values[column]
    return frame
