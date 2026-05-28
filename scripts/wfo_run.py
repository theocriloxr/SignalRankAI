#!/usr/bin/env python3
"""Run Walk-Forward Optimization over Parquet datasets.

Usage examples:
  python -m scripts.wfo_run --input-dir ./data/parquet --assets BTCUSDT,ETHUSDT --timeframes 5m,1h --start 2021-01-01 --end 2021-06-01

The script heuristically loads parquet files from the input directory. Filenames should include the asset and timeframe, e.g. BTCUSDT_5m.parquet or BTCUSDT|5m.parquet. Tick-level files may include 'tick' in their name.
"""
import argparse
import os
from pathlib import Path
from datetime import datetime
import pandas as pd

from engine.backtest import BacktestRunner
from engine.wfo import WalkForwardOptimizer


def load_parquet_files(input_dir: Path):
    files = list(input_dir.glob('*.parquet'))
    mapping = []
    for f in files:
        name = f.stem
        # heuristics: split by | or _ or -
        for sep in ['|', '_', '-']:
            if sep in name:
                parts = name.split(sep)
                if len(parts) >= 2:
                    asset = parts[0].upper()
                    tf = parts[1]
                    mapping.append((asset, tf, f))
                    break
        else:
            # fallback: skip
            continue
    return mapping


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input-dir', required=True)
    p.add_argument('--assets', required=True, help='comma separated assets to include')
    p.add_argument('--timeframes', required=True, help='comma separated timeframes')
    p.add_argument('--start', required=True)
    p.add_argument('--end', required=True)
    p.add_argument('--model-path', required=False)
    args = p.parse_args()

    input_dir = Path(args.input_dir)
    assets = [a.strip().upper() for a in args.assets.split(',') if a.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(',') if t.strip()]
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)

    runner = BacktestRunner()

    files = load_parquet_files(input_dir)
    for asset, tf, path in files:
        if asset in assets and tf in timeframes:
            df = pd.read_parquet(path)
            # tick file heuristic
            if 'tick' in path.stem.lower():
                runner.register_tick_dataframe(asset, tf, df)
            else:
                runner.register_dataframe(asset, tf, df)

    wfo = WalkForwardOptimizer(runner)

    def train_cb(signals, df_map):
        # use built-in trainer
        return wfo.default_train_xgb(signals, df_map)

    results = wfo.run(assets, timeframes, train_months=3, test_months=1, start=start, end=end, train_callback=train_cb)
    for r in results:
        print(r)


if __name__ == '__main__':
    main()
