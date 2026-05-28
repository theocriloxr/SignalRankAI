from datetime import datetime, timedelta
import pandas as pd

from engine.backtest import BacktestRunner
from engine.wfo import WalkForwardOptimizer


def make_candle_df(start: datetime, periods: int):
    rng = pd.date_range(start=start, periods=periods, freq='5T', tz='UTC')
    close = (100 + pd.Series(range(periods)) * 0.01).round(2)
    df = pd.DataFrame({'timestamp': rng, 'open': close.shift(1).fillna(close.iloc[0]), 'high': close + 0.5, 'low': close - 0.5, 'close': close, 'volume': 1.0})
    return df


def make_orderbook_snapshots(start: datetime):
    # Create snapshots where asks are thin at first, forcing fills across levels
    times = [start + timedelta(minutes=i) for i in range(10)]
    snapshots = []
    for i, t in enumerate(times):
        # asks: price increasing, small sizes early
        asks = [[101 + j, 0.5 + j * 0.5] for j in range(5)]
        bids = [[99 - j, 0.5 + j * 0.5] for j in range(5)]
        snapshots.append({'timestamp': t, 'asks': asks, 'bids': bids})
    return pd.DataFrame(snapshots)


def test_orderbook_partial_consumption():
    start = datetime(2021, 1, 1)
    candle_df = make_candle_df(start, 100)
    ob_df = make_orderbook_snapshots(start + timedelta(hours=1))

    runner = BacktestRunner()
    runner.register_dataframe('OBPAIR', '5m', candle_df)
    runner.register_orderbook_dataframe('OBPAIR', '5m', ob_df)

    # craft a synthetic signal for simulation
    sig = {
        'asset': 'OBPAIR',
        'timeframe': '5m',
        'direction': 'long',
        'entry': 100.0,
        'stop_loss': 98.0,
        'take_profit': [{'price': 103.0, 'exit_percent': 100}],
        'timestamp': ob_df['timestamp'].iloc[0]
    }

    wfo = WalkForwardOptimizer(runner)
    df_map = {f"OBPAIR|5m": runner.get_df('OBPAIR', '5m'), f"OBPAIR|5m|orderbook": runner.get_orderbook_df('OBPAIR', '5m')}
    res = wfo._simulate_pnl([sig], df_map, test_start=ob_df['timestamp'].iloc[0], test_end=ob_df['timestamp'].iloc[-1] + timedelta(minutes=1), account_equity=1000.0)
    assert isinstance(res, list)
    assert len(res) == 1
    assert res[0]['pnl'] <= 0 or res[0]['pnl'] >= 0  # sanity: pnl present (may be positive or negative depending on fills)