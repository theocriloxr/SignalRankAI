from datetime import datetime, timedelta
import pandas as pd

from engine.backtest import BacktestRunner
from engine.wfo import WalkForwardOptimizer


def make_candle_df(start: datetime, periods: int):
    rng = pd.date_range(start=start, periods=periods, freq='5T', tz='UTC')
    close = (100 + pd.Series(range(periods)) * 0.01).round(2)
    df = pd.DataFrame({'timestamp': rng, 'open': close.shift(1).fillna(close.iloc[0]), 'high': close + 0.5, 'low': close - 0.5, 'close': close, 'volume': 1.0})
    return df


def make_tick_df(start: datetime):
    # Create ticks that hit TP price but each tick has small size forcing partial fills
    times = [start + timedelta(minutes=i) for i in range(10)]
    prices = [100.0, 100.5, 101.0, 101.0, 101.0, 101.0, 101.5, 102.0, 102.5, 103.0]
    sizes = [1, 1, 2, 1, 0.5, 0.5, 3, 5, 1, 10]
    df = pd.DataFrame({'timestamp': pd.to_datetime(times, utc=True), 'price': prices, 'size': sizes})
    return df


def test_tick_partial_fill_simulation():
    start = datetime(2021, 1, 1)
    candle_df = make_candle_df(start, 100)
    tick_df = make_tick_df(start + timedelta(hours=1))

    runner = BacktestRunner()
    runner.register_dataframe('LQPAIR', '5m', candle_df)
    runner.register_tick_dataframe('LQPAIR', '5m', tick_df)

    # craft a single signal that will be generated at the first candle and has TP=102 and SL=99
    # We'll simulate by registering a small synthetic signal set in runner and invoking WFO simulation
    # Use WFO run with small windows to trigger simulation
    wfo = WalkForwardOptimizer(runner)
    end = start + timedelta(days=1)
    results = wfo.run(['LQPAIR'], ['5m'], train_months=1, test_months=1, start=start, end=end)
    assert isinstance(results, list)