# SignalRankAI

## Railway monolith production notes

### Migrations
- Runtime auto-migration is disabled by default (`AUTO_MIGRATE=false`).
- Run migrations in deploy/release step:
  - `python -m alembic upgrade head`

### Monolith tuning defaults
- Engine cadence: `ENGINE_CYCLE_SLEEP_SECONDS=30`
- Universe cap (mixed open-market assets): `ENGINE_UNIVERSE_CAP=20`
- Logging profile: essential (loop/webhook noise moved to debug-level)
- Telegram mode: webhook-only on Railway
- Outcome tracker ownership: worker-only

### DB hardening defaults (balanced mode)
- `DB_POOL_SIZE=5`
- `DB_MAX_OVERFLOW=3`
- `DB_POOL_TIMEOUT_SECONDS=30`
- `DB_POOL_RECYCLE_SECONDS=1800`
- `DB_RETRY_ATTEMPTS=3`

## Backtest and orderbook snapshot formats

### Candle data
- Expected columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`.
- `timestamp` should be parseable by pandas and is normalized to UTC in the loader.

### Tick data
- Expected columns: `timestamp`, `price`, and one of `size`, `qty`, or `volume`.
- Tick files may include `tick` in the filename, but the loader also detects the schema automatically.

### Orderbook data
- Preferred normalized schema: `timestamp`, `bids`, `asks`.
- `bids` and `asks` should contain JSON arrays or Python lists of `[price, size]` pairs.
- Common exchange exports are also supported:
  - Top-of-book: `bidPrice`, `bidQty`, `askPrice`, `askQty`
  - Flattened depth: `bid_price_1`, `bid_size_1`, `ask_price_1`, `ask_size_1`, etc.
- The WFO CLI can normalize raw orderbook files to parquet with:

```bash
python -m scripts.wfo_run --input-dir ./raw_orderbooks --assets BTCUSDT --timeframes 5m --start 2021-01-01 --end 2021-02-01 --convert-orderbooks --normalized-output-dir ./normalized_orderbooks
```

### WFO CLI auto-detection
- `scripts/wfo_run.py` now auto-detects candle, tick, and orderbook snapshots by filename and schema.
- Orderbook inputs are registered via `register_orderbook_dataframe()` automatically when `bids`/`asks` or common book columns are present.

