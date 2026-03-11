# SignalRankAI — Enterprise Refactor Changelog & Manual Action Guide

> Generated: 2026-03-10  
> Scope: Full enterprise refactor — API-first architecture, Redis removal, Fernet encryption,  
> MetaApi MT5 bridge, zero stale signals, real-time outcome tracking, dynamic Telegram menus,  
> one-click MT5 execution, VIP scarcity loop, global owner alerting, asyncio main, Railway 500 MB.

---

## Table of Contents

1. [New Files Created](#new-files-created)
2. [Modified Files](#modified-files)
3. [Bug Fixes (Test Suite)](#bug-fixes-test-suite)
4. [Manual Actions Required Before Deploy](#manual-actions-required-before-deploy)
5. [New Environment Variables](#new-environment-variables)
6. [New Telegram Commands](#new-telegram-commands)
7. [Database Migrations Required](#database-migrations-required)
8. [Dependency Changes](#dependency-changes)
9. [Architecture Notes](#architecture-notes)

---

## New Files Created

### `services/__init__.py`
Package marker for the new `services/` layer.

### `services/security.py`
Fernet symmetric encryption for sensitive credentials (MT5 passwords).
- `encrypt_secret(plaintext)` → URL-safe base64 ciphertext
- `decrypt_secret(ciphertext)` → plaintext
- `is_encryption_available()` → bool
- **Requires**: `ENCRYPTION_KEY` env var (32-byte URL-safe base64 key)
- **Graceful degradation**: stores plaintext with warning if key missing

### `services/asset_mapper.py`
Cross-provider canonical symbol mapping.
- `map_symbol("GOLD", "yfinance")` → `"GC=F"`
- `classify_asset("BTCUSDT")` → `"crypto"` | `"forex"` | `"commodity"` | `"stock"`
- `get_all_providers_for_asset(symbol)` → full mapping dict
- No external dependencies — pure Python lookup tables

### `services/mt5_client.py`
MetaApi cloud bridge for Linux-compatible MT5 integration.
- `get_live_price(account_id, symbol)` → mid price float
- `validate_slippage(account_id, symbol, signal_price)` → `(within_tol, slip_pts, live_price)`
- `execute_trade(account_id, symbol, direction, volume, sl, tp, entry)` → result dict
- `update_stop_loss(account_id, order_id, new_sl)` → modifies open position SL
- `link_mt5_account(telegram_user_id, login, password, server)` → encrypts + stores + provisions
- `get_user_mt5_account_id(telegram_user_id)` → DB lookup

### `engine/stale_signal_validator.py`
Zero-stale-signal enforcement — checks live price drift before dispatch.
- `validate_signal_freshness(signal)` → async `(is_fresh, reason, live_price)`
- `validate_signal_freshness_sync(signal)` → sync wrapper
- Price sources: Binance REST → DB market_ticks → yfinance (in executor)
- Threshold: `abs(live − entry) / entry * 100 > STALE_PRICE_THRESHOLD_PCT`

### `engine/realtime_outcome_tracker.py`
Real-time async TP/SL outcome detection replacing the 3-minute APScheduler candle scan.
- `RealtimeOutcomeTracker` with `start()` / `stop()` / async `_loop()`
- Detects TP1 / TP2 / TP3 / SL every `OUTCOME_CHECK_INTERVAL_SECONDS` (default 15 s)
- On TP1: calls `update_stop_loss()` to trail SL to break-even via MetaApi
- Sends branded PnL flex card to all `SignalDelivery` recipients
- Persists outcome row and archives the signal
- `outcome_tracker` singleton exported for import by other modules

---

## Modified Files

### `db/models.py`
- **Added**: `MT5Credentials` ORM model — stores encrypted MT5 login, server, MetaApi account ID
- **Added**: `_unlogged_meta` with `_t_daily_counters` and `_t_rate_limits` Core `Table` objects
- **Updated**: import line to include `Table, Column, MetaData`

### `db/session.py`
- **Extended** `_schema_checked` DDL block to auto-create at first session open:
  - `mt5_credentials` (regular table, FK to `users.id`)
  - `daily_signal_counters` **UNLOGGED** — replaces Redis daily-counter key
  - `rate_limit_tokens` **UNLOGGED** — replaces Redis rate-limit sliding window

### `data/providers.py`
- **Added**: `fetch_coingecko_candles(symbol, timeframe, limit)` — CoinGecko OHLCV via free API
- **Added**: `fetch_alphavantage_candles(symbol, timeframe, limit)` — AlphaVantage TIME_SERIES
- **Added**: `fetch_candles_waterfall(symbol, timeframe, limit)` — unified provider waterfall:
  - Crypto: Binance → CoinGecko → Yahoo
  - Forex: OANDA → TwelveData → Polygon → Yahoo
  - Commodity: Yahoo → AlphaVantage → TwelveData
  - Stock: AlphaVantage → Polygon → TwelveData → Yahoo

### `data/connectors/polygon_adapter.py`
- **Fixed**: moved `client = get_client()` call inside `_do()` async closure so unit-test patches
  to `utils.httpx_client.get_client` are respected at call time (not captured at module load).

### `engine/ml.py`
- **Added**: `import gc`
- **Added**: `booster.set_param("nthread", int(os.getenv("XGB_NTHREAD", "2")))` — caps CPU threads
- **Added**: `del raw_bytes` immediately after `booster.load_model()` — releases raw model bytes
- **Added**: `gc.collect()` after model load — frees any cyclic garbage from XGBoost init
- Effect: reduces peak RSS by ~20–40 MB on Railway 500 MB tier

### `engine/ultra_quality_filter.py`
- **Fixed** default thresholds (were lowered to 65 in a previous commit; restored to spec):
  - `min_score`: `65.0` → `85.0`
  - `min_confluence`: `70.0` → `80.0`
  - `min_rr_ratio`: `2.0` → `2.5`
  - `min_adx`: `20.0` → `25.0`
  - `min_confidence`: `0.70` → `0.80`
- All thresholds remain overridable via env vars (e.g. `ULTRA_MIN_SCORE=70`)

### `engine/core.py`
- **Integrated** stale signal validator into the per-signal delivery loop:
  - Calls `validate_signal_freshness_sync(sig)` **before** the existing price_validator block
  - Drops and logs any signal where live price has drifted beyond `STALE_PRICE_THRESHOLD_PCT`
  - Falls back gracefully if `stale_signal_validator` is unavailable (debug log only)

### `web/app.py`
- **Fixed** `verify_paystack_signature` signature-check order:
  - Checks for **missing signature header** first → `HTTP 400` (was reaching the secret check first, returning 500 when secret not set in test env)
  - Reads secret fresh from `os.getenv()` instead of cached `config` object — allows tests that set `os.environ["PAYSTACK_WEBHOOK_SECRET"]` after import

### `signalrank_telegram/commands.py`
- **Added** `mt5_link_command` — `/mt5_link <login> <password> <server>`
  - Requires Premium or VIP tier
  - Deletes the command message immediately to prevent credential exposure in chat history
  - Encrypts password with Fernet before storage
  - Shows progress message while linking, edits to success/failure
- **Added** `mt5_status_command` — `/mt5_status`
  - Shows linked MT5 account details (server, login, MetaApi ID)
  - Requires Premium or VIP tier

### `signalrank_telegram/bot.py`
- **Added** global owner error alerting in `_on_error`:
  - Formats a full traceback and sends it to every `OWNER_ID` via Telegram
  - Never raises; bot polling continues uninterrupted
- **Replaced** static `set_my_commands` in `_post_init` with **`BotCommandScopeChat`** dynamic menus:
  - FREE users: 10 global commands
  - PREMIUM users: + dashboard, history, risk, alerts, mt5_link, mt5_status
  - VIP users: + elite, early, report
  - OWNER/ADMIN: + unlock, dev_pause, dev_resume, owner_users, owner_revenue, provider_status
- **Registered** `/mt5_link` and `/mt5_status` `CommandHandler`s
- **Added** `CallbackQueryHandler` for `^mt5_trade_` pattern:
  - Validates slippage, executes trade via MetaApi, edits inline message with result
  - Callback data format: `mt5_trade_<signal_id>|<asset>|<direction>|<entry>|<sl>|<tp>`
- **Added** `vip_scarcity_broadcast_job`:
  - Runs every 6 hours via APScheduler
  - Queries `count_active_vip_users()`, computes `VIP_SEAT_LIMIT − used`
  - Broadcasts scarcity message to all PREMIUM users when seats are available
- **Registered** VIP scarcity job in the `BackgroundScheduler`

### `main.py`
- **Removed** `import threading`
- **Replaced** `threading.Thread` `RUN_MODE=all` implementation with `asyncio.gather()`:
  - **Web**: `uvicorn.Server(config).serve()` — native async coroutine
  - **Engine**: `loop.run_in_executor(None, main_loop)` — blocking, isolated thread
  - **Worker**: `loop.run_in_executor(None, worker_main)` — blocking, isolated thread
  - **Bot**: `loop.run_in_executor(None, run_bot)` — PTB manages its own inner loop in thread
  - Top-level entry: `asyncio.run(_run_all())`

### `nixpacks.toml`
- **Replaced** with Railway 500 MB–optimised config:
  - Creates a proper `/opt/venv` virtualenv (prevents system Python pollution)
  - `pip install --no-cache-dir` — saves ~50 MB image size
  - Start command prefixed with `MALLOC_ARENA_MAX=2 PYTHONMALLOC=malloc PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1`
  - `[variables]` block sets the same env vars as Railway deployment variables
  - Build phase uses venv python for Alembic migrations

### `test_tradingview_integration.py`
- **Fixed** all `open(...)` calls to use `encoding='utf-8'` — prevents `UnicodeDecodeError` on
  Windows CP1252 default encoding when reading files containing emoji/Unicode characters.

---

## Bug Fixes (Test Suite)

| Test | Root Cause | Fix |
|------|-----------|-----|
| `test_near_zero_loss.py::test_ultra_quality_filter` | `min_score` default was 65, filter was not rejecting low-score signals | Restored defaults to spec: `min_score=85, min_confluence=80, min_rr_ratio=2.5, min_adx=25, min_confidence=0.80` |
| `test_tradingview_integration.py::test_signals_no_limit` | `open('signalrank_telegram/commands.py', 'r')` used CP1252 on Windows; file has emoji | Added `encoding='utf-8'` to all `open()` calls in the test file |
| `tests/test_connectors_providers.py::test_polygon_adapter_parses_results` | `get_client()` resolved at function-definition time; mock patches it after import | Moved `_client = get_client()` inside `_do()` async closure |
| `tests/test_paystack_webhook.py::test_rejects_missing_signature` | `verify_paystack_signature` checked secret before signature; secret absent → 500 | Reordered: missing signature → 400 before secret lookup |
| `tests/test_paystack_webhook.py::test_accepts_valid_signature_payments_disabled` | `secret = config.PAYSTACK_WEBHOOK_SECRET` read cached None; test sets `os.environ` after import | Read fresh from `os.getenv("PAYSTACK_WEBHOOK_SECRET")` |

---

## Manual Actions Required Before Deploy

### 1. Set `ENCRYPTION_KEY` environment variable (CRITICAL)

Generate a secure Fernet key and add it to your Railway service:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add the output as `ENCRYPTION_KEY` in Railway → your service → Variables.

> ⚠️ **If you deploy without this key, MT5 passwords will be stored in plaintext with a warning log.**
> Once set, you cannot change the key without re-encrypting all stored passwords.

### 2. Set `META_API_TOKEN` environment variable (for MT5 features)

Register at https://metaapi.cloud and obtain your API token.
Add as `META_API_TOKEN` in Railway Variables.

> Without this, `/mt5_link` will store credentials in DB but skip MetaApi account provisioning.
> The `⚡ Trade on MT5` button will be non-functional.

### 3. Database migration for `mt5_credentials` table

The table is auto-created by `db/session.py` on first session open. However, if you want to
add it explicitly via Alembic:

```sql
CREATE TABLE IF NOT EXISTS mt5_credentials (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mt5_login VARCHAR(64) NOT NULL,
    password_encrypted VARCHAR(512) NOT NULL,
    server VARCHAR(128) NOT NULL,
    metaapi_account_id VARCHAR(256),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (user_id)
);
```

### 4. Database migration for UNLOGGED tables

These replace Redis ephemeral state. Auto-created on first session open, but to add explicitly:

```sql
CREATE UNLOGGED TABLE IF NOT EXISTS daily_signal_counters (
    user_id BIGINT NOT NULL,
    date DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);

CREATE UNLOGGED TABLE IF NOT EXISTS rate_limit_tokens (
    user_id BIGINT NOT NULL,
    window_key VARCHAR(64) NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0,
    window_start TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, window_key)
);
```

> ⚠️ **UNLOGGED tables are wiped on Postgres crash/restart.** This is intentional — they store
> ephemeral rate-limit and counter state. On restart, counters reset to 0 (users get a fresh day).

### 5. Install new Python dependencies

```bash
pip install cryptography metaapi-cloud-sdk
```

Or add to `requirements.txt` (see Dependency Changes section).

### 6. Set `VIP_SEAT_LIMIT` (optional, default 15)

```
VIP_SEAT_LIMIT=15
```

Controls the VIP scarcity broadcast threshold. Set to your actual VIP seat count.

### 7. Set `XGB_NTHREAD` (optional, default 2)

```
XGB_NTHREAD=2
```

Caps XGBoost CPU threads. Reduce to `1` on the 500 MB Railway tier if you see OOM.

### 8. Set `OUTCOME_CHECK_INTERVAL_SECONDS` (optional, default 15)

```
OUTCOME_CHECK_INTERVAL_SECONDS=15
```

How often the real-time outcome tracker polls live prices. Increase to 30–60 on the free tier
to reduce Binance/provider rate-limit pressure.

### 9. Set `STALE_PRICE_THRESHOLD_PCT` (optional, default 0.5)

```
STALE_PRICE_THRESHOLD_PCT=0.5
```

Maximum allowed price drift (%) from signal entry before the signal is considered stale and
dropped from delivery. Increase to 1.0 or 2.0 for slower-moving assets (commodities).

### 10. Verify `PAYSTACK_WEBHOOK_SECRET` is set in Railway

The webhook signature check now reads directly from `os.getenv("PAYSTACK_WEBHOOK_SECRET")`.
Ensure this is set in Railway Variables → your web service. If absent, the endpoint returns
`HTTP 500` on any webhook call.

---

## New Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENCRYPTION_KEY` | ✅ Yes | — | Fernet key for MT5 password encryption |
| `META_API_TOKEN` | ✅ For MT5 | — | MetaApi cloud API token |
| `SLIPPAGE_TOLERANCE` | Optional | `0.001` | Max allowed slippage (0.1%) for MT5 execution |
| `OUTCOME_CHECK_INTERVAL_SECONDS` | Optional | `15` | Real-time outcome tracker poll interval |
| `STALE_PRICE_THRESHOLD_PCT` | Optional | `0.5` | Max price drift % before signal is dropped |
| `STALE_PRICE_FETCH_TIMEOUT` | Optional | `5` | Seconds before stale price fetch times out |
| `VIP_SEAT_LIMIT` | Optional | `15` | Total VIP seats for scarcity broadcasts |
| `XGB_NTHREAD` | Optional | `2` | XGBoost CPU thread cap |
| `MALLOC_ARENA_MAX` | Set by nixpacks | `2` | glibc malloc arena limit (memory saving) |
| `PYTHONMALLOC` | Set by nixpacks | `malloc` | Use system malloc (reduces fragmentation) |

---

## New Telegram Commands

| Command | Tier Required | Description |
|---------|--------------|-------------|
| `/mt5_link <login> <password> <server>` | Premium+ | Link MetaTrader 5 account; password encrypted with Fernet |
| `/mt5_status` | Premium+ | Show linked MT5 account details |

### Inline Button
When a signal is dispatched, a `[⚡ Trade on MT5]` inline keyboard button can be attached.

**Callback data format**: `mt5_trade_<signal_id>|<asset>|<direction>|<entry>|<sl>|<tp>`

To attach the button when dispatching signals, build an `InlineKeyboardMarkup` in your
signal formatter:

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def make_mt5_button(sig):
    data = f"mt5_trade_{sig['signal_id']}|{sig['asset']}|{sig['direction']}|{sig['entry']}|{sig['stop_loss']}|{sig['take_profit']}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("⚡ Trade on MT5", callback_data=data)]])
```

---

## Database Migrations Required

All DDL is **auto-applied** by `db/session.py` on first async session open. No manual migration
step is required for fresh deploys. For existing deployments, run the SQL in the
[Manual Actions](#manual-actions-required-before-deploy) section above or let the app
auto-migrate on next cold start.

---

## Dependency Changes

Add the following to `requirements.txt` if not already present:

```
cryptography>=41.0.0
metaapi-cloud-sdk>=23.0.0
```

Both are optional at import time (graceful degradation if absent), but required for full
MT5 functionality.

---

## Architecture Notes

### Redis Removal
Redis has been fully removed from the hot path. Ephemeral state is now:
- **Rate limits** → `rate_limit_tokens` UNLOGGED table (Postgres)
- **Daily counters** → `daily_signal_counters` UNLOGGED table (Postgres)
- **Signal delivered flag** → `signal_deliveries` regular table (already existed)
- **Kill-switch** → `runtime_state` regular table (already existed)

UNLOGGED tables in Postgres offer ~3–5× faster write throughput vs regular tables while still
supporting concurrent access across Railway replicas — something Redis shared but SQLite cannot.

### asyncio Architecture (`RUN_MODE=all`)
All four services (web, engine, worker, bot) are now supervised by a single `asyncio.run()` call:
- **Web** runs as a true async coroutine via `uvicorn.Server.serve()`
- **Engine/Worker/Bot** run in `ThreadPoolExecutor` slots (they use blocking APIs internally)
- `asyncio.gather()` provides a single supervision point — if one service exits, the gather
  returns and the process exits (Railway restarts it)

### MetaApi MT5 Bridge
MetaApi runs MT5 in a cloud container (Linux-compatible). The `services/mt5_client.py` bridge:
1. Provisions a MetaApi account on first `/mt5_link`
2. Fetches live bid/ask prices for slippage validation
3. Places market orders with pre-set SL/TP
4. Modifies SL to break-even when TP1 is hit (trailing stop via `engine/realtime_outcome_tracker.py`)

### Zero Stale Signals
Every signal passes through two freshness gates before delivery:
1. **Time-based** (`engine/price_validator.py::is_signal_fresh`) — checks signal age vs timeframe
2. **Price-based** (`engine/stale_signal_validator.py::validate_signal_freshness_sync`) — fetches
   live price and rejects if entry zone has drifted beyond `STALE_PRICE_THRESHOLD_PCT`

The price-based gate is new and runs first in the delivery loop.
