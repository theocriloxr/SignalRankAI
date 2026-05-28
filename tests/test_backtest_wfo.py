import pandas as pd
from datetime import datetime, timedelta

from engine.backtest import BacktestRunner
from engine.wfo import WalkForwardOptimizer


def make_synthetic_df(start: datetime, periods: int, freq: str = '5T') -> pd.DataFrame:
    rng = pd.date_range(start=start, periods=periods, freq=freq, tz='UTC')
    close = (100 + (pd.Series(range(periods)) * 0.01)).round(2)
    df = pd.DataFrame({
        'timestamp': rng,
        'open': close.shift(1).fillna(close.iloc[0]),
        'high': close + 0.5,
        'low': close - 0.5,
        'close': close,
        'volume': 1.0,
    })
    return df


def test_backtest_and_wfo_basic():
    start = datetime(2021, 1, 1)
    df = make_synthetic_df(start, periods=500, freq='5T')
    runner = BacktestRunner()
    runner.register_dataframe('TESTPAIR', '5m', df)

    bt = runner.run_backtest(['TESTPAIR'], ['5m'], start + timedelta(hours=1), start + timedelta(hours=10))
    # should return a dict with the asset key
    assert isinstance(bt, dict)

    wfo = WalkForwardOptimizer(runner)
    end = start + timedelta(days=3)
    # simple run without ML callback
    results = wfo.run(['TESTPAIR'], ['5m'], train_months=1, test_months=1, start=start, end=end)
    assert isinstance(results, list)


def test_wfo_with_dummy_train_callback():
    start = datetime(2021, 1, 1)
    df = make_synthetic_df(start, periods=500, freq='5T')
    runner = BacktestRunner()
    runner.register_dataframe('TESTPAIR', '5m', df)
    wfo = WalkForwardOptimizer(runner)

    def dummy_trainer(signals, df_map):
        # returns a predictor that gives 0.6 probability for every signal
        def predict(sig):
            return 0.6
        return predict

    end = start + timedelta(days=3)
    results = wfo.run(['TESTPAIR'], ['5m'], train_months=1, test_months=1, start=start, end=end, train_callback=dummy_trainer)
    assert isinstance(results, list)