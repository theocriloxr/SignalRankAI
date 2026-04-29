"""Startup self-checks for market data connectivity.

Purpose:
- Emit clear, actionable warnings in logs if market-data providers are unreachable.
- Never crash the process (fail-open), so Railway logs show the issue and the
  engine/bot can continue (or run with reduced coverage).

Controls:
- STARTUP_DATA_CHECK=true|false (default true)
- STARTUP_DATA_CHECK_VERBOSE=true|false (default false)
"""

from __future__ import annotations

import os
import time
from typing import Optional

import requests


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


import logging
logger = logging.getLogger(__name__)

def _log(msg: str) -> None:
    logger.info(msg)


def _warn(msg: str) -> None:
    logger.warning(msg)


def _info(msg: str) -> None:
    logger.info(msg)


def _binance_symbol_rest(asset: str) -> str:
    a = (asset or "").upper().strip()
    a = a.replace("/", "").replace("-", "")
    if a.endswith("USD") and not a.endswith("USDT"):
        a = a[:-3] + "USDT"
    return a


def _first_crypto_symbol() -> str:
    raw = (os.getenv("TRADABLE_ASSETS") or "").strip()
    if raw:
        for x in raw.split(","):
            sym = _binance_symbol_rest(x)
            if sym.endswith(("USDT", "USDC", "BUSD")) and len(sym) >= 6:
                return sym
    return "BTCUSDT"


def check_binance(timeout_seconds: float = 6.0) -> bool:
    """Return True if Binance appears reachable."""
    symbol = _first_crypto_symbol()

    # Use klines as a stronger check than /ping.
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "1h", "limit": 2}
    try:
        resp = requests.get(url, params=params, timeout=timeout_seconds)
        if not resp.ok:
            try:
                payload = resp.json()
            except Exception:
                payload = None
            msg = None
            try:
                if isinstance(payload, dict):
                    msg = str(payload.get("msg") or payload.get("message") or "")
            except Exception:
                msg = None

            msg_l = (msg or "").lower()
            if "restricted location" in msg_l or "not available" in msg_l or "not supported" in msg_l:
                _warn(
                    "Binance appears geo-blocked in this environment (restricted location). "
                    "Action: change Railway region (or network) or switch crypto data provider. "
                    f"HTTP {resp.status_code} | symbol={symbol} | msg={msg}"
                )
            else:
                _warn(f"Binance unreachable or blocked: HTTP {resp.status_code} | symbol={symbol} | payload={payload}")
            return False
        payload = resp.json()
        if not isinstance(payload, list) or not payload:
            # Binance errors can come back as dict payloads.
            msg = None
            try:
                if isinstance(payload, dict):
                    msg = str(payload.get("msg") or payload.get("message") or "")
            except Exception:
                msg = None

            msg_l = (msg or "").lower()
            if "restricted location" in msg_l or "not available" in msg_l or "not supported" in msg_l:
                _warn(
                    "Binance appears geo-blocked in this environment (restricted location). "
                    "Action: change Railway region (or network) or switch crypto data provider. "
                    f"symbol={symbol} | msg={msg}"
                )
            else:
                _warn(f"Binance returned unexpected klines payload for {symbol}: {payload}")
            return False
        return True
    except Exception as e:
        _warn(f"Binance request failed (network/DNS/timeout): {e}")
        return False


def check_alphavantage(timeout_seconds: float = 8.0) -> Optional[bool]:
    """Return True/False if check was performed, or None if not applicable."""
    fx_pairs = (os.getenv("FX_PAIRS") or "").strip()
    api_key = (os.getenv("ALPHAVANTAGE_API_KEY") or "").strip()

    if not fx_pairs:
        return None

    if not api_key:
        _warn("FX_PAIRS is set but ALPHAVANTAGE_API_KEY is missing. FX candles will be disabled.")
        return False

    # Use a lightweight FX_DAILY call (still 1 API call).
    try:
        first_pair = next((p.strip().upper() for p in fx_pairs.split(",") if p.strip()), "EURUSD")
    except Exception:
        first_pair = "EURUSD"

    if len(first_pair) < 6:
        first_pair = "EURUSD"

    from_symbol, to_symbol = first_pair[:3], first_pair[3:6]

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "FX_DAILY",
        "from_symbol": from_symbol,
        "to_symbol": to_symbol,
        "outputsize": "compact",
        "apikey": api_key,
    }

    try:
        resp = requests.get(url, params=params, timeout=timeout_seconds)
        payload = resp.json() if resp.ok else {}
        if not resp.ok:
            _warn(f"AlphaVantage unreachable: HTTP {resp.status_code} | pair={first_pair} | payload={payload}")
            return False

        # AlphaVantage often returns throttling messages with HTTP 200.
        if any(k in payload for k in ("Note", "Information", "Error Message")):
            _warn(f"AlphaVantage returned throttle/error payload for {first_pair}: {payload}")
            return False

        series = payload.get("Time Series FX (Daily)")
        if not isinstance(series, dict) or not series:
            _warn(f"AlphaVantage returned empty daily series for {first_pair}: {payload}")
            return False

        return True
    except Exception as e:
        _warn(f"AlphaVantage request failed (network/DNS/timeout): {e}")
        return False


def run_startup_data_selfcheck() -> None:
    if not _env_bool("STARTUP_DATA_CHECK", True):
        return

    verbose = _env_bool("STARTUP_DATA_CHECK_VERBOSE", False)

    crypto_provider = (os.getenv("CRYPTO_DATA_PROVIDER") or "").strip().lower()

    # Binance
    if crypto_provider == "cryptocompare":
        if verbose:
            _info("Market data self-check: Binance skipped (CRYPTO_DATA_PROVIDER=cryptocompare)")
    else:
        ok_binance = check_binance()
        if ok_binance:
            if verbose:
                _info("Market data self-check: Binance reachable")
        else:
            _warn(
                "Market data self-check: Binance NOT reachable. "
                "If you're on Railway and Binance is geo-blocked, signals will be reduced/empty. "
                "Consider changing region or swapping data provider."
            )

    # AlphaVantage (only if FX is configured)
    ok_alpha = check_alphavantage()
    if ok_alpha is None:
        if verbose:
            _info("Market data self-check: AlphaVantage skipped (FX_PAIRS not set)")
    elif ok_alpha:
        if verbose:
            _info("Market data self-check: AlphaVantage reachable")
    else:
        # Warning already emitted in the checker.
        pass

    # Tiny sleep so logs appear before rapid thread startup in RUN_MODE=all.
    time.sleep(0.05)
