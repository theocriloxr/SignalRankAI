# Production Hardening, Freshness, DB, and Tiering Fix — 2026-07-11

## Why this pass exists
Recent logs showed the bot could generate and deliver signals, but still had production-level problems:

- old/stale entries could be labelled Fresh and sent after TP/SL was already invalidated;
- Telegram commands and buttons competed with engine/outcome jobs for DB sessions;
- background features were enabled but treated as best-effort noncritical work, causing repeated `NoncriticalWriteDropped` noise;
- `/signals`, `/profile_debug`, `/outcome`, and buttons needed interactive DB priority;
- tier messaging did not clearly explain why users should upgrade;
- live price routing had a stock/FX mapping bug where normal tickers could be converted to `META=X`-style symbols.

## Best-practice principles applied

1. **Fail closed before sending trading alerts.** If the bot cannot prove that a signal is fresh at delivery time, it should not send it.
2. **Use a fresh quote for final-send validation.** Do not rely only on the candle payload that generated the signal.
3. **Never let background tasks starve user actions.** Interactive Telegram commands/buttons get priority; heavy jobs run behind caps.
4. **Keep Telegram callbacks instant.** Acknowledge callbacks immediately, then send a visible result message.
5. **Make tiers about workflow value.** Free proves the product, Premium gives usable trading workflow, VIP gives priority/automation-grade controls.
6. **Use correct provider symbol mapping.** Stocks should stay `META`, FX should map to `EURUSD=X`, commodities to futures/commodity symbols, crypto to crypto pairs.

## Code changes

### `data/get_live_price.py`
- Fixed Yahoo endpoint from `/charts/` to `/chart/`.
- Fixed Yahoo symbol routing via `services.asset_mapper.map_symbol`.
- Prevented stocks like `META` from being converted into `META=X`.
- Avoided blocking the async event loop by moving `requests.get()` calls into `asyncio.to_thread()`.
- Crypto now has `binance -> bybit -> cryptocompare -> yahoo` fallback; non-crypto uses `yahoo -> polygon`.

### `engine/delivery_freshness.py`
- Added final-send live price gate.
- Added strict per-asset drift thresholds:
  - crypto: `0.20%`
  - forex: `0.08%`
  - stock: `0.35%`
  - commodity: `0.20%`
  - index: `0.25%`
- Blocks signals when TP1/all targets are already consumed before send.
- Blocks if live price is unavailable when `DELIVERY_REQUIRE_LIVE_PRICE=1`.
- Stops stale/missed entries such as BNB/META/XAU from reaching Telegram as “Fresh.”

### `signalrank_telegram/bot.py`
- Delivery freshness timeout/error now fails closed by default.
- Removed duplicate formatter call.
- Active signal message persistence now uses `critical=True`, not `noncritical=True`, so message tracking is not dropped under background pressure.

### `db/session.py`
- `/db_health` now uses an interactive-priority session.

### `signalrank_telegram/commands.py`
- Telegram command DB reads now use `interactive=True` sessions.
- Pricing/upgrade copy now better differentiates Free, Premium, and VIP.
- Pricing is sent with HTML parse mode.

## Required env values

```env
FINAL_SEND_LIVE_PRICE_CHECK_ENABLED=1
FINAL_SEND_FORCE_FRESH_PRICE=1
FINAL_SEND_LIVE_PRICE_TIMEOUT_SECONDS=4
FINAL_SEND_LIVE_PRICE_MAX_CACHE_SECONDS=10
DELIVERY_REQUIRE_LIVE_PRICE=1
DELIVERY_FRESHNESS_TIMEOUT_FAIL_OPEN=0
DELIVERY_FRESHNESS_ERROR_FAIL_OPEN=0
REJECT_IF_TP1_ALREADY_HIT=1
REJECT_IF_ALL_TARGETS_ALREADY_HIT=1
FINAL_SEND_MAX_DRIFT_CRYPTO_PCT=0.20
FINAL_SEND_MAX_DRIFT_FOREX_PCT=0.08
FINAL_SEND_MAX_DRIFT_STOCK_PCT=0.35
FINAL_SEND_MAX_DRIFT_COMMODITY_PCT=0.20
FINAL_SEND_MAX_DRIFT_INDEX_PCT=0.25
DELIVERY_MIN_CURRENT_RR=1.0
```

Recommended supervised DB scale-up profile:

```env
DB_POOL_SIZE=8
DB_MAX_OVERFLOW=4
DB_MAX_CONCURRENT_SESSIONS=10
DB_POOL_SIZE_RAILWAY=8
DB_MAX_OVERFLOW_RAILWAY=4
DB_POOL_DISABLE_RAILWAY_CAP=1
DB_POOL_ALLOW_UNCAPPED_RAILWAY=1
DB_BACKGROUND_MAX_CONCURRENT_SESSIONS=3
DB_BACKGROUND_SESSION_GATE_TIMEOUT_SECONDS=3
DB_BACKGROUND_DROP_WHEN_BUSY=1
DB_INTERACTIVE_SESSION_GATE_TIMEOUT_SECONDS=8
DB_INTERACTIVE_PAUSES_BACKGROUND=1
DB_CRITICAL_SESSION_GATE_TIMEOUT_SECONDS=60
DB_NONCRITICAL_DROP_WHEN_CRITICAL_ACTIVE=0
DB_NONCRITICAL_WRITE_DROP_ON_GATE_TIMEOUT=1
```

## What good logs should show

```text
[delivery] blocked stale signal ... final_entry_drift:...
[delivery] blocked stale signal ... tp1_already_hit_before_send
[telegram_send_ok]
[delivery_proof_write] sent_ok=True message_id=...
[dispatch_sent_ok]
[callback_ack] answered
[check_outcome] user=... ok=True
```

## What should disappear or reduce

```text
META/XAU/BNB signals sent far away from live price
Fresh signals with TP already passed
[active_message_save_failed] noncritical DB write dropped
[cmd:signals] timed out
Profile debug failed: NoncriticalWriteDropped
```
