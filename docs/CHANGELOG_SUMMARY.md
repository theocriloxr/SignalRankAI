# Changelog Summary

_Generated at 2026-04-05T09:52:59.770012+00:00_

## Latest Snapshot

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
