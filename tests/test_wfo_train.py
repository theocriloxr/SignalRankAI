from datetime import datetime, timedelta
import pandas as pd

from engine.backtest import BacktestRunner
from engine.wfo import WalkForwardOptimizer


def make_synthetic_df(start: datetime, periods: int, freq: str = '5T') -> pd.DataFrame:
    rng = pd.date_range(start=start, periods=periods, freq=freq, tz='UTC')
    close = (100 + (pd.Series(range(periods)) * 0.1)).round(2)
    df = pd.DataFrame({
        'timestamp': rng,
        'open': close.shift(1).fillna(close.iloc[0]),
        'high': close + 0.5,
        'low': close - 0.5,
        'close': close,
        'volume': 1.0,
    })
    return df


def test_wfo_train_and_predict():
    start = datetime(2021, 1, 1)
    df = make_synthetic_df(start, periods=1000, freq='5T')
    runner = BacktestRunner()
    runner.register_dataframe('TRAINPAIR', '5m', df)
    wfo = WalkForwardOptimizer(runner)

    def trainer(signals, df_map):
        # use the default trainer provided by WFO
        return wfo.default_train_xgb(signals, df_map)

    end = start + timedelta(days=10)
    results = wfo.run(['TRAINPAIR'], ['5m'], train_months=1, test_months=1, start=start, end=end, train_callback=trainer)
    assert isinstance(results, list)