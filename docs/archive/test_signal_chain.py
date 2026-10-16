"""Live full signal-chain smoke test."""

import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DATA_TESTS", "0").strip().lower() not in {"1", "true", "yes"},
    reason="live signal-chain smoke test requires RUN_LIVE_DATA_TESTS=1",
)
def test_live_signal_chain_generates_or_explicitly_rejects():
    os.environ["CANDLE_REQUEST_CACHE_TTL_SECONDS"] = "0.1"

    from data.fetcher import get_candles
    from data.indicators import calculate_indicators
    from engine.consensus import apply_consensus_filter
    from engine.scoring import calculate_signal_score
    from strategies import run_all_strategies

    asset = "BTCUSDT"
    timeframe = "1h"
    candles = get_candles(asset, timeframe)

    assert candles

    indicators = calculate_indicators(candles)
    market_data = {timeframe: {"candles": candles, "indicators": indicators}}
    signals = run_all_strategies(asset, market_data, "TRENDING")

    from engine.signal_controller import SignalController

    normalized = SignalController().normalize_signals(signals)
    consensus_signals = apply_consensus_filter(normalized)
    scored = []
    for sig in consensus_signals:
        sig["score"] = calculate_signal_score(sig)
        scored.append(sig)

    assert isinstance(scored, list)


if __name__ == "__main__":
    raise SystemExit("Run with pytest and RUN_LIVE_DATA_TESTS=1 for live signal-chain validation.")
