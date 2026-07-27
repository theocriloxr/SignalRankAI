from __future__ import annotations

import threading
import time
from datetime import datetime, timezone


def _candles(count: int = 25) -> list[dict]:
    return [
        {
            "timestamp": 1_700_000_000 + i * 300,
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100.5 + i,
            "volume": 10,
        }
        for i in range(count)
    ]


def test_inflight_candle_requests_are_coalesced(monkeypatch) -> None:
    import data.fetcher as fetcher

    fetcher._CANDLE_CACHE.clear()
    fetcher._CANDLE_INFLIGHT.clear()
    calls = 0
    calls_lock = threading.Lock()

    def fake_chain(asset: str, timeframe: str):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.08)
        return _candles()

    monkeypatch.setattr(fetcher, "get_asset_type", lambda _asset: "crypto")
    monkeypatch.setattr(fetcher, "_fetch_crypto_multi_provider", fake_chain)
    monkeypatch.setenv("USE_MULTI_PROVIDER_DATA", "true")
    monkeypatch.setenv("CANDLE_REQUEST_CACHE_TTL_SECONDS", "5")

    results: list[list] = []
    threads = [
        threading.Thread(target=lambda: results.append(fetcher.get_candles("BTCUSDT", "5m")))
        for _ in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert calls == 1
    assert len(results) == 5
    assert all(len(result) == 25 for result in results)


def test_provider_chain_attempts_are_bounded(monkeypatch) -> None:
    import data.fetcher as fetcher

    attempted: list[str] = []

    def make_provider(name: str):
        def _provider(timeout: float = 0):
            attempted.append(name)
            return []
        return _provider

    monkeypatch.setenv("OHLC_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME", "2")
    monkeypatch.setenv("OHLC_DEFAULT_PROVIDER_MAX_CONCURRENCY", "1")
    result = fetcher._try_provider_chain(
        [(f"p{i}", make_provider(f"p{i}")) for i in range(5)],
        asset="TEST",
        timeframe="5m",
        asset_kind="test",
    )

    assert result == []
    assert attempted == ["p0", "p1"]


def test_provider_semaphore_enforces_configured_limit(monkeypatch) -> None:
    import data.fetcher as fetcher

    monkeypatch.setenv("COINBASE_OHLC_MAX_CONCURRENCY", "2")
    fetcher._SYNC_PROVIDER_SEMAPHORES.clear()
    fetcher._SYNC_PROVIDER_LIMITS.clear()
    fetcher._PROVIDER_INFLIGHT.clear()

    active = 0
    max_active = 0
    guard = threading.Lock()

    def provider(timeout: float = 0):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return _candles()

    threads = [
        threading.Thread(
            target=lambda: fetcher._run_provider_request(
                "coinbase_connector", provider, asset="BTCUSDT", timeframe="5m"
            )
        )
        for _ in range(6)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert max_active == 2
    assert fetcher.get_provider_concurrency_snapshot()["coinbase"]["inflight"] == 0


def test_registry_classifies_problem_symbols_without_us_stock_fallback() -> None:
    from core.asset_registry import resolve_asset_spec

    assert resolve_asset_spec("USDTIDR").asset_class == "crypto"
    assert resolve_asset_spec("DOGEIDR").session_calendar == "crypto_24_7"
    assert resolve_asset_spec("USDTARS").subtype == "crypto_fiat"
    assert resolve_asset_spec("JP225").session_calendar == "japan_equity"
    assert resolve_asset_spec("FRA40").session_calendar == "europe_equity"
    assert resolve_asset_spec("EU50").session_calendar == "europe_equity"
    assert resolve_asset_spec("AUS200").session_calendar == "australia_equity"
    assert resolve_asset_spec("HK50").session_calendar == "hong_kong_equity"
    assert resolve_asset_spec("DXY").analysis_only is True
    assert resolve_asset_spec("US10Y").actionable is False
    assert resolve_asset_spec("XAUTUSDT").subtype == "tokenised_commodity"
    assert resolve_asset_spec("not-a-real-market-symbol-123").asset_class == "unknown"


def test_market_sessions_use_registry_and_fail_closed(monkeypatch) -> None:
    from data.market_hours import get_market_session_status

    saturday = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    assert get_market_session_status("USDTIDR", saturday).is_open is True

    jp = get_market_session_status("JP225", saturday)
    assert jp.is_open is False
    assert jp.calendar == "japan_equity"

    macro = get_market_session_status("DXY", saturday)
    assert macro.is_open is False
    assert macro.session == "analysis_only"

    unknown = get_market_session_status("123!", saturday)
    assert unknown.is_open is False
    assert unknown.reason == "DISABLED_BAD_CLASSIFICATION"


def test_fx_overlap_detection_is_reachable(monkeypatch) -> None:
    # Contract-level assertion: the overlap condition must precede the broad
    # NEW_YORK branch so it cannot become unreachable again.
    from pathlib import Path

    source = Path("market/session_classifier.py").read_text(encoding="utf-8")
    overlap_index = source.index("if 13 <= hour < 17")
    new_york_index = source.index("if 17 <= hour < 22")
    assert overlap_index < new_york_index
