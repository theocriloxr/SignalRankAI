#!/usr/bin/env python3
"""Run Walk-Forward Optimization over raw or normalized market datasets.

Supported inputs:
- Candle parquet/csv/json with OHLCV columns
- Tick parquet/csv/json with `timestamp`, `price`, and optional `size`/`qty`/`volume`
- Orderbook parquet/csv/json with either:
  - `timestamp`, `bids`, `asks` columns containing level lists, or
  - flattened columns like `bid_price_1`, `bid_size_1`, `ask_price_1`, `ask_size_1`, or
  - top-of-book columns like `bidPrice`, `bidQty`, `askPrice`, `askQty`

Examples:
  python -m scripts.wfo_run --input-dir ./data/parquet --assets BTCUSDT,ETHUSDT --timeframes 5m,1h --start 2021-01-01 --end 2021-06-01
  python -m scripts.wfo_run --input-dir ./raw_orderbooks --convert-orderbooks --normalized-output-dir ./normalized --assets BTCUSDT --timeframes 5m --start 2021-01-01 --end 2021-06-01
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

from engine.backtest import BacktestRunner
from engine.wfo import WalkForwardOptimizer


ORDERBOOK_HINTS = ("orderbook", "order_book", "depth", "book", "l2", "lob")
TICK_HINTS = ("tick", "trades", "trade")


def _infer_asset_timeframe(stem: str) -> tuple[Optional[str], Optional[str]]:
    parts = re.split(r"[|_\-]", stem)
    if len(parts) >= 2:
        return parts[0].upper(), parts[1]
    return None, None


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                return json.loads(text)
            except Exception:
                return value
    return value


def _normalize_levels(value: Any) -> list[list[float]]:
    value = _maybe_json(value)
    levels: list[list[float]] = []
    if isinstance(value, list):
        for item in value:
            try:
                if isinstance(item, dict):
                    price = item.get("price") or item.get("px") or item.get("rate")
                    size = item.get("size") or item.get("qty") or item.get("volume") or item.get("amount")
                    levels.append([float(price), float(size)])
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    levels.append([float(item[0]), float(item[1])])
            except Exception:
                continue
    return levels


def normalize_orderbook_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize common exchange orderbook formats into `timestamp`, `bids`, `asks` columns."""
    out = df.copy()
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
        out = out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    else:
        raise ValueError("orderbook dataframe must contain a timestamp column")

    if "bids" in out.columns and "asks" in out.columns:
        out["bids"] = out["bids"].apply(_normalize_levels)
        out["asks"] = out["asks"].apply(_normalize_levels)
        return out

    # Top-of-book common format
    top_bid_price = next((c for c in ("bidPrice", "bid_price", "best_bid", "bid") if c in out.columns), None)
    top_bid_qty = next((c for c in ("bidQty", "bid_qty", "bidSize", "bid_size", "bid_volume") if c in out.columns), None)
    top_ask_price = next((c for c in ("askPrice", "ask_price", "best_ask", "ask") if c in out.columns), None)
    top_ask_qty = next((c for c in ("askQty", "ask_qty", "askSize", "ask_size", "ask_volume") if c in out.columns), None)
    if top_bid_price and top_ask_price:
        out["bids"] = out.apply(lambda r: [[float(r[top_bid_price]), float(r[top_bid_qty] if top_bid_qty else 0.0)]], axis=1)
        out["asks"] = out.apply(lambda r: [[float(r[top_ask_price]), float(r[top_ask_qty] if top_ask_qty else 0.0)]], axis=1)
        return out[["timestamp", "bids", "asks"]]

    # Flattened multi-level format (bid_price_1, bid_size_1, ask_price_1, ask_size_1...)
    bid_price_cols = sorted([c for c in out.columns if re.match(r"^bid[_]?price[_]?\d+$", c, re.I)], key=lambda c: int(re.sub(r"\D", "", c) or 0))
    bid_size_cols = sorted([c for c in out.columns if re.match(r"^bid[_]?(?:size|qty|volume)[_]?[0-9]+$", c, re.I)], key=lambda c: int(re.sub(r"\D", "", c) or 0))
    ask_price_cols = sorted([c for c in out.columns if re.match(r"^ask[_]?price[_]?\d+$", c, re.I)], key=lambda c: int(re.sub(r"\D", "", c) or 0))
    ask_size_cols = sorted([c for c in out.columns if re.match(r"^ask[_]?(?:size|qty|volume)[_]?[0-9]+$", c, re.I)], key=lambda c: int(re.sub(r"\D", "", c) or 0))
    if bid_price_cols and ask_price_cols:
        def _row_levels(row, price_cols, size_cols):
            levels = []
            for idx, pcol in enumerate(price_cols):
                scol = size_cols[idx] if idx < len(size_cols) else None
                try:
                    price = row[pcol]
                    if pd.isna(price):
                        continue
                    size = row[scol] if scol else 0.0
                    levels.append([float(price), float(size if not pd.isna(size) else 0.0)])
                except Exception:
                    continue
            return levels

        out["bids"] = out.apply(lambda r: _row_levels(r, bid_price_cols, bid_size_cols), axis=1)
        out["asks"] = out.apply(lambda r: _row_levels(r, ask_price_cols, ask_size_cols), axis=1)
        return out[["timestamp", "bids", "asks"]]

    raise ValueError("unsupported orderbook schema")


def is_orderbook_frame(df: pd.DataFrame, path: Path | None = None) -> bool:
    cols = {str(c) for c in df.columns}
    if {"bids", "asks"}.issubset(cols):
        return True
    if any(c in cols for c in ("bidPrice", "askPrice", "bid_price_1", "ask_price_1")):
        return True
    if path is not None:
        stem = path.stem.lower()
        if any(h in stem for h in ORDERBOOK_HINTS):
            return True
    return False


def is_tick_frame(df: pd.DataFrame, path: Path | None = None) -> bool:
    cols = {str(c) for c in df.columns}
    if {"timestamp", "price"}.issubset(cols) and any(c in cols for c in ("size", "qty", "volume")):
        return True
    if path is not None:
        stem = path.stem.lower()
        if any(h in stem for h in TICK_HINTS):
            return True
    return False


def load_dataset_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".tsv"}:
        return pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
    if suffix in {".json", ".ndjson", ".jsonl"}:
        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return pd.DataFrame(data if isinstance(data, list) else [data])
        return pd.read_json(path, lines=True)
    raise ValueError(f"unsupported file type: {path.suffix}")


def convert_orderbook_file(input_path: Path, output_path: Path) -> Path:
    df = load_dataset_file(input_path)
    normalized = normalize_orderbook_frame(df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_parquet(output_path, index=False)
    return output_path


def discover_inputs(input_dir: Path):
    for path in sorted(input_dir.iterdir()):
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".parquet", ".csv", ".tsv", ".json", ".jsonl", ".ndjson"}:
            continue
        stem = path.stem
        asset, tf = _infer_asset_timeframe(stem)
        kind = "orderbook" if any(h in stem.lower() for h in ORDERBOOK_HINTS) else ("tick" if any(h in stem.lower() for h in TICK_HINTS) else "candle")
        yield asset, tf, kind, path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input-dir', required=True)
    p.add_argument('--assets', required=True, help='comma separated assets to include')
    p.add_argument('--timeframes', required=True, help='comma separated timeframes')
    p.add_argument('--start', required=True)
    p.add_argument('--end', required=True)
    p.add_argument('--normalized-output-dir', required=False, help='optional parquet output dir for normalized orderbook snapshots')
    p.add_argument('--convert-orderbooks', action='store_true', help='normalize detected orderbook inputs to parquet before backtesting')
    args = p.parse_args()

    input_dir = Path(args.input_dir)
    assets = [a.strip().upper() for a in args.assets.split(',') if a.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(',') if t.strip()]
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    normalized_output_dir = Path(args.normalized_output_dir) if args.normalized_output_dir else None

    runner = BacktestRunner()

    for asset, tf, kind, path in discover_inputs(input_dir):
        if asset and asset not in assets:
            continue
        if tf and tf not in timeframes:
            continue
        df = load_dataset_file(path)

        if kind == 'orderbook' or is_orderbook_frame(df, path):
            normalized = normalize_orderbook_frame(df)
            runner.register_orderbook_dataframe(asset or path.stem.upper(), tf or '1m', normalized)
            if args.convert_orderbooks and normalized_output_dir is not None:
                out_name = f"{(asset or path.stem).upper()}_{tf or 'orderbook'}_orderbook.parquet"
                normalized_output_dir.mkdir(parents=True, exist_ok=True)
                normalized.to_parquet(normalized_output_dir / out_name, index=False)
        elif kind == 'tick' or is_tick_frame(df, path):
            runner.register_tick_dataframe(asset or path.stem.upper(), tf or '1m', df)
        else:
            # Best effort candle normalization: ensure timestamp sorting if present
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
                df = df.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
            runner.register_dataframe(asset or path.stem.upper(), tf or '1m', df)

    wfo = WalkForwardOptimizer(runner)

    def train_cb(signals, df_map):
        # use built-in trainer
        return wfo.default_train_xgb(signals, df_map)

    results = wfo.run(assets, timeframes, train_months=3, test_months=1, start=start, end=end, train_callback=train_cb)
    for r in results:
        print(r)


if __name__ == '__main__':
    main()
