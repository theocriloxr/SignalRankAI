# Crypto-only exit runbook

Keep `CRYPTO_ONLY_MODE=1` and `ASSET_CLASSES_ENABLED=crypto` until all five gates remain healthy for 12–24 hours.

1. Market data: `market_data_assets > 0`, at least 10/20 preferred, and `no_candles_crypto < 30%`.
2. Scoring: `strategy_signals > 0`, `normalized > 0`, and `max_score_pre_threshold` is present.
3. Delivery: at least one stored candidate has `sent_ok=true`, a Telegram chat ID, and a message ID.
4. Lifecycle: a delivered signal records `entry_touched` and one terminal/progression event, with one successful event notification.
5. Database: session-gate timeouts are rare or absent; noncritical decision/rejection writes remain disabled if pressure continues.

Do not promote when any cycle returns `market_data:no_assets_returned`, formatter failures repeat, delivery proof is absent, or DB gate timeouts remain frequent.

## Staged promotion

Promote one phase at a time and roll back on worsening candle failure rates, cycle duration, delivery, lifecycle, or DB pressure.

1. Crypto: `CRYPTO_ONLY_MODE=1`, `ASSET_CLASSES_ENABLED=crypto`
2. Crypto + FX: `CRYPTO_ONLY_MODE=0`, `ASSET_CLASSES_ENABLED=crypto,fx`
3. Add commodities: `ASSET_CLASSES_ENABLED=crypto,fx,commodity`
4. Add indices: `ASSET_CLASSES_ENABLED=crypto,fx,commodity,index`
5. Add stocks during market hours: `ASSET_CLASSES_ENABLED=crypto,fx,commodity,index,stock`

After every phase, require another sustained clean observation window before promotion.
