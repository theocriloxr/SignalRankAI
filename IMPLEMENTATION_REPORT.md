# GENESIS OMNI-PROMPT — Implementation Report

**Date:** 2026-03-11  
**Project:** SignalRankAI  
**Scope:** Full SaaS Enterprise Feature Buildout

---

## 1. Overview

This report documents every change made during the GENESIS OMNI-PROMPT implementation session. All changes are backward-compatible additions; no existing behavior was removed.

---

## 2. New Files Created

| File | Purpose |
|------|---------|
| `services/economic_calendar.py` | Macro news protector — Finnhub API + 30-min no-trade zone |
| `engine/tiered_executor.py` | PREMIUM/VIP execution logic — lot sizing, daily caps, multi-stage TPs |
| `tests/test_enterprise_features.py` | 11 test classes, ~35 assertions covering all new features |

---

## 3. Modified Files

### `db/models.py`
New **User** columns:
- `referred_by` — `BigInteger`, the referrer's `telegram_user_id` (nullable)
- `fixed_lot_size` — `Float`, default `0.01` (PREMIUM fixed lot)
- `daily_executions_today` — `Integer`, default `0`
- `daily_executions_reset_at` — `DateTime`, nullable (UTC reset timestamp)
- `max_risk_percentage` — `Float`, default `1.0` (VIP risk %)

New **Signal** columns:
- `expires_at` — `DateTime`, indexed, nullable (set to `now + 12h` at creation)
- `expired` — `Boolean`, default `False`, indexed
- `is_near_order_block` — `Boolean`, default `False`

New tables:
- **`SignalEngagement`** — stores 🔥 / 👀 reactions per user/signal (UNIQUE constraint)
- **`ActiveSignalMessage`** — tracks `message_id` + `chat_id` per dispatched signal for inline edits
- **`EconomicEvent`** — cached high-impact economic events (Finnhub)
- **`MT5Execution`** — full execution record per trade (lot, entry, TP/SL, realized PnL, status)
- **`VIPWaitlist`** — users waiting for a VIP seat (UNIQUE on `user_id`)

> **Manual action required:** Run the Alembic migration or execute the `manual_migration_*.sql` file to add these columns/tables to your existing PostgreSQL database.

---

### `data/market_data.py`
- Added `format_ticker(symbol, provider)` — unified mapper for yfinance, Binance, Oanda, Polygon, TwelveData, MetaApi
- Added `fetch_candles_with_circuit_breaker(symbol, timeframe)` — async `asyncio.wait_for(timeout=3s)` waterfall: Binance REST → yfinance → failure
- Added `detect_order_blocks(candles, lookback=100)` — Fair Value Gap / imbalance detection, returns `bool`
- Kept `_convert_to_yfinance_symbol()` as a deprecated shim delegating to `format_ticker`

---

### `web/app.py`
- Added `logger = logging.getLogger(__name__)`
- Updated `paystack_webhook`: on VIP-full, auto-adds buyer to `VIPWaitlist` instead of raising 409
- Updated `paystack_webhook`: calls `_apply_referral_bonus()` after a successful subscription
- Added `_add_to_vip_waitlist(telegram_user_id)` — idempotent insert into `vip_waitlist`
- Added `_apply_referral_bonus(event)` — looks up `User.referred_by`, extends referrer's active `Subscription.expires_at` by `REFERRAL_BONUS_DAYS` (default 7)
- Added `create_paystack_checkout(uid, tier, amount_ngn, ...)` — calls Paystack `/transaction/initialize`, returns `{"url": ..., "reference": ...}`
- Added `POST /upgrade` endpoint — generates dynamic Paystack checkout link; checks VIP capacity first

---

### `signalrank_telegram/commands.py`
New commands appended after `mt5_status_command`:

| Command | Tier | Description |
|---------|------|-------------|
| `/setlot <0.001–1.0>` | PREMIUM+ | Set fixed lot size; stored on `User.fixed_lot_size` |
| `/setrisk <0.1–5.0>` | VIP only | Set risk % per trade; stored on `User.max_risk_percentage` |
| `/tiers` | All | HTML comparison table: FREE / PREMIUM ₦15k / VIP ₦30k |
| `/mystats` | All | Personal P&L: win rate, total PnL, executions, sub expiry |
| `/referral` | All | Deep-link generator + referral count + bonus days earned |
| `/connect_broker` | PREMIUM+ | FSM (ConversationHandler, 4-step): login → password → server → confirm |

`help_command` now appends a tier-specific command section:
- FREE → upgrade CTA (`/tiers`, `/upgrade`, `/referral`)  
- PREMIUM → `/setlot`, `/connect_broker`, `/mt5_status`, `/mystats`, `/referral`  
- VIP/OWNER/ADMIN → all PREMIUM + `/setrisk`

---

### `signalrank_telegram/bot.py`
- Registered all new commands: `setlot`, `setrisk`, `tiers`, `mystats`, `referral`, `connect_broker`  
- Added `CallbackQueryHandler(pattern=r"^signal_reaction_")` — handles 🔥/👀 inline buttons, persists to `SignalEngagement` table
- Updated `_post_init` command menus (PREMIUM + VIP levels include new commands)
- Added **FOMO engine job** (`fomo_engine_job`) — daily at 17:00 UTC, broadcasts today's VIP P&L total to all FREE users
- Added **Friday leaderboard job** (`friday_leaderboard_job`) — Fridays at 17:00 UTC, broadcasts Top 3 VIP traders by weekly PnL
- Added **signal auto-expiry job** (`expire_old_signals_job`) — every 30 min, bulk-sets `Signal.expired = True` where `expires_at ≤ now`

---

## 4. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PREMIUM_PRICE_NGN` | `15000` | PREMIUM subscription price in Nigerian Naira |
| `VIP_PRICE_NGN` | `30000` | VIP subscription price in Nigerian Naira |
| `VIP_SEAT_LIMIT` | `15` | Maximum concurrent VIP subscribers |
| `REFERRAL_BONUS_DAYS` | `7` | Extra days granted to referrer on successful referral |
| `PREMIUM_DAILY_EXECUTIONS` | `3` | Max automated MT5 executions per day for PREMIUM |
| `DEFAULT_FIXED_LOT` | `0.01` | Default lot size for PREMIUM users |
| `DEFAULT_RISK_PCT` | `1.0` | Default risk % for VIP users |
| `MAX_RISK_PCT` | `5.0` | Maximum allowed risk % |
| `PREMIUM_MAX_LOT` | `1.0` | Maximum lot for PREMIUM |
| `VIP_MAX_LOT` | `10.0` | Maximum lot for VIP |
| `FINNHUB_API_KEY` | *(none)* | Finnhub API key for economic calendar (free tier OK) |
| `NO_TRADE_BUFFER_MINUTES` | `30` | Blackout window around high-impact USD events |
| `PAYSTACK_CALLBACK_URL` | *(none)* | Paystack callback URL after payment |
| `BOT_USERNAME` | `SignalRankBot` | Telegram bot username (for deep links) |

---

## 5. Manual Database Migration

Run the following SQL against your PostgreSQL database **before deploying**:

```sql
-- User table additions
ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS fixed_lot_size FLOAT DEFAULT 0.01;
ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_today INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_reset_at TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS max_risk_percentage FLOAT DEFAULT 1.0;

-- Signal table additions
ALTER TABLE signals ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS expired BOOLEAN DEFAULT FALSE;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS is_near_order_block BOOLEAN DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS ix_signals_expires_at ON signals (expires_at);
CREATE INDEX IF NOT EXISTS ix_signals_expired ON signals (expired);

-- New tables
CREATE TABLE IF NOT EXISTS signal_engagements (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_user_id),
    signal_id INTEGER NOT NULL REFERENCES signals(id),
    reaction VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, signal_id)
);

CREATE TABLE IF NOT EXISTS active_signal_messages (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_user_id),
    signal_id INTEGER NOT NULL REFERENCES signals(id),
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS economic_events (
    id SERIAL PRIMARY KEY,
    event_date TIMESTAMP,
    currency VARCHAR(10),
    title VARCHAR(255),
    impact VARCHAR(10),
    source VARCHAR(50),
    fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mt5_executions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_user_id),
    signal_id INTEGER REFERENCES signals(id),
    metaapi_account_id VARCHAR(100),
    order_id VARCHAR(100),
    symbol VARCHAR(20),
    direction VARCHAR(10),
    lot_size FLOAT,
    entry_price FLOAT,
    stop_loss FLOAT,
    take_profit FLOAT,
    status VARCHAR(30) DEFAULT 'pending',
    tier_at_execution VARCHAR(20),
    realized_pnl FLOAT,
    realized_pnl_pct FLOAT,
    executed_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    meta JSONB
);

CREATE TABLE IF NOT EXISTS vip_waitlist (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(telegram_user_id),
    joined_at TIMESTAMP DEFAULT NOW(),
    notified_at TIMESTAMP
);
```

---

## 6. Architecture Decisions

### Async circuit-breaker waterfall (`fetch_candles_with_circuit_breaker`)
Using `asyncio.wait_for(timeout=3.0)` on every provider call ensures a hung upstream (Binance GFW block, Finnhub rate limit) never stalls the engine for more than 3 seconds per provider.

### Tiered execution isolation
PREMIUM and VIP execution paths are completely separate (`execute_premium_signal` vs `execute_vip_signal`) — this avoids accidental privilege escalation and makes the daily limit logic trivially auditable.

### FSM-style `/connect_broker`
Using PTB's `ConversationHandler` with a 300 s timeout prevents orphan states from accumulating. The password message is immediately deleted from the chat after receipt.

### Referral system
Referral bonus is applied server-side at the point of first payment (webhook), not at link-click — this is phishing-resistant and idempotent (the `Subscription.expires_at` update is done via SQLAlchemy `update()` not an `INSERT`).

### VIP waitlist vs. hard rejection
Previously a VIP-full payment returned a 409 error and the money was not charged. The new flow adds the user to the `vip_waitlist` *before* returning 409 so that when a seat opens we can proactively notify them.

### Economic calendar caching
Events are cached in-process for 1 hour (`_CACHE_TTL_SECONDS = 3600`) to avoid hammering Finnhub's free tier. The `force_refresh=True` flag lets admin commands bypass the cache.

---

## 7. Test Coverage Summary

| Test Class | Assertions | What is tested |
|-----------|-----------|---------------|
| `TestPaystackWebhookFlow` | 4 | Signature validation (missing/bad/valid/no-secret) |
| `TestPaystackCheckoutLink` | 2 | Checkout URL generation + missing secret |
| `TestLotSizePremium` | 4 | Fixed lot: default, custom, min clamp, max clamp |
| `TestLotSizeVIP` | 5 | Risk-based: EURUSD, XAUUSD, min/max clamp, zero balance |
| `TestPremiumExecutionLimit` | 5 | Daily cap, new-day reset, VIP unlimited, FREE blocked |
| `TestSignalAutoExpiry` | 3 | expires_at column, 12h math, is_near_order_block column |
| `TestVIPWaitlist` | 2 | Model columns, noop when ENGINE=None |
| `TestReferralBonus` | 2 | Noop without engine, noop with missing uid |
| `TestEconomicCalendar` | 3 | Non-USD passthrough, within buffer, outside buffer |
| `TestFormatTicker` | 8 | All provider mappings + edge cases |
| `TestDetectOrderBlocks` | 4 | Empty, insufficient, bullish FVG, no FVG |

Run with:
```bash
pytest tests/test_enterprise_features.py -v
```

---

## 8. Deployment Checklist

- [ ] Run manual SQL migration (Section 5)
- [ ] Set `FINNHUB_API_KEY` environment variable
- [ ] Set `PREMIUM_PRICE_NGN=15000` and `VIP_PRICE_NGN=30000`
- [ ] Set `VIP_SEAT_LIMIT=15` (or desired capacity)
- [ ] Set `REFERRAL_BONUS_DAYS=7`
- [ ] Set `PAYSTACK_CALLBACK_URL` to your success redirect page
- [ ] Set `BOT_USERNAME` to match your BotFather username
- [ ] Test `/connect_broker` FSM end-to-end in staging
- [ ] Test Paystack checkout via `/upgrade` endpoint
- [ ] Verify FOMO job fires correctly at 17:00 UTC (check Railway cron logs)
- [ ] Confirm `/tiers`, `/mystats`, `/referral` display correctly per tier
