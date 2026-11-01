"""Pegged / reserve-backed crypto exclusion (1 Nov 2026).

Production evidence: the discovered crypto universe was mostly stablecoins and
tokenized reserves, and the serving model scored them highest. They must be
excluded from scanning and training; real coins, forex and commodities must not
be affected.
"""
from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from core.pegged_assets import crypto_base, filter_pegged, is_pegged_crypto


@pytest.mark.parametrize(
    "symbol",
    [
        "USDCUSDT", "USDTBUSDT", "USDUUSDT", "USDXUSDT", "PYUSDUSDT", "RLUSDUSDT", "CRVUSDUSDT",
        "DUSDUSDT", "EUSDUSDT", "BTCUSDUSDT", "PAXGUSDT", "XAUTUSDT", "BUIDLUSDT", "EURCUSDT",
        "EURSAFOUSDT", "EUTBLUSDT", "DOLAUSDT", "A7A5USDT", "FDUSDUSDT", "USDS-USDT", "PYUSD/USDT",
    ],
)
def test_pegged_tokens_are_recognised(symbol):
    assert is_pegged_crypto(symbol)


@pytest.mark.parametrize(
    "symbol",
    ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "SUIUSDT", "AAVEUSDT", "DUSDT", "BRUSDT", "USELESSUSDT",
     "EURUSD", "USDJPY", "XAUUSD", "XAGUSD", "US500", "NVDA"],
)
def test_real_instruments_are_not_pegged(symbol):
    assert not is_pegged_crypto(symbol)


def test_crypto_base_strips_quote():
    assert crypto_base("PYUSDUSDT") == "PYUSD"
    assert crypto_base("btc-usdt") == "BTC"


def test_filter_only_touches_crypto_quoted_symbols(monkeypatch):
    monkeypatch.delenv("PEGGED_ASSET_FILTER_ENABLED", raising=False)
    universe = ["BTCUSDT", "PYUSDUSDT", "EURUSD", "XAUUSD", "XAUTUSDT", "NVDA", "usdcusdt"]
    assert filter_pegged(universe) == ["BTCUSDT", "EURUSD", "XAUUSD", "NVDA"]


def test_filter_can_be_disabled_and_extended(monkeypatch):
    monkeypatch.setenv("PEGGED_ASSET_FILTER_ENABLED", "0")
    assert filter_pegged(["PYUSDUSDT"]) == ["PYUSDUSDT"]
    monkeypatch.setenv("PEGGED_ASSET_FILTER_ENABLED", "1")
    monkeypatch.setenv("PEGGED_ASSET_EXTRA_BASES", "BEAN")
    assert filter_pegged(["BEANUSDT", "BTCUSDT"]) == ["BTCUSDT"]


def test_pair_discovery_drops_pegged_pairs():
    from data.pair_discovery import _filter_blacklisted

    assert _filter_blacklisted(["BTCUSDT", "PYUSDUSDT", "USDTBUSDT", "ETHUSDT"]) == ["BTCUSDT", "ETHUSDT"]


def test_training_rows_exclude_pegged_assets():
    from ml.train_model import _exclude_pegged_assets

    df = pd.DataFrame(
        {"asset": ["BTCUSDT", "PAXGUSDT", "PYUSDUSDT", "EURUSD", "XAUUSD"], "target": [1, 1, 1, 0, 0]}
    )
    df.attrs["read_status"] = "success"
    kept, evidence = _exclude_pegged_assets(df)
    assert list(kept["asset"]) == ["BTCUSDT", "EURUSD", "XAUUSD"]
    assert evidence["rows_removed"] == 2
    assert kept.attrs["read_status"] == "success"


def test_database_universe_never_returns_pegged_crypto():
    from data.database_universe import load_database_universe

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, statement, params):
            self.calls += 1
            if self.calls > 1:
                return _Result([])
            return _Result([("BTCUSDT",), ("EURUSD",), ("PYUSDUSDT",), ("USDTBUSDT",)])

    symbols = asyncio.run(load_database_universe(_Session(), page_size=250))
    assert symbols == ["BTCUSDT", "EURUSD"]
