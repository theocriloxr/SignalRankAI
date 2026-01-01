# SignalRankAI — Full Functional Specification

This document captures the complete functional specification for SignalRankAI (Telegram signals product), including purpose, behavior, and implementation notes.

## 1) User Management & Access Control

### User Registration
**What it does**
- Registers every user on first interaction.

**How it works**
- Triggered on `/start`.
- Stores:
  - `telegram_id`
  - `username`
  - `joined_at`
  - `tier = FREE` (default when no active subscription)
- Persisted to Postgres (required). No SQLite fallback.

**Why**
- Enables access control, monetization, analytics, and abuse prevention.

### Tier Detection
**What it does**
- Determines what the user can see/do.

**How it works**
- On every command:
  - Check subscription table
  - Check expiry date
  - Check owner bypass
  - Return tier: `FREE / PREMIUM / VIP / OWNER`

### Owner Bypass
**What it does**
- Gives the owner full access.

**How it works**
- Matches Telegram user id against `OWNER_TELEGRAM_ID` / `OWNER_IDS`.
- Supports `/unlock <BYPASS_KEY>` (session-based temporary elevation).

## 2) Market Data Ingestion

### Crypto Data Feed
**What it does**
- Fetches real-time crypto market data.

**How it works**
- Primary: Binance WebSocket streams
  - tickers
  - candles
- Fallback: REST endpoints
- Uses async connections
- Auto-reconnect logic

### FX Data Feed
**What it does**
- Fetches forex market data.

**How it works**
- REST polling (OANDA / AlphaVantage)
- Scheduled every timeframe
- Cached to avoid API limits

### Data Normalization
**What it does**
- Converts raw price data into a unified format.

**How it works**
- Standard OHLCV schema
- Time-aligned per timeframe
- Stored temporarily in cache

## 3) Strategy Engine (Core Intelligence)

### Strategy Evaluation
**What it does**
- Runs multiple strategies per asset/timeframe.

**How it works**
- Each strategy module:
  - receives candles
  - returns a signal or `None`
- Strategy families:
  - Trend
  - Momentum
  - Volatility
  - Structure

### Market Regime Detection
**What it does**
- Identifies trending vs ranging vs volatile markets.

**How it works**
- Uses ADX, ATR, Bollinger Band width
- Determines allowed strategy types

## 4) Signal Consensus & Filtering

### Signal Consensus
**What it does**
- Prevents weak/random trades.

**How it works**
- Requires:
  - ≥ 3 agreeing strategies
  - mandatory category coverage
  - direction alignment

### Higher Timeframe Alignment
**What it does**
- Confirms LTF trades with HTF bias.

**How it works**
- Evaluate HTF trend
- Reject signals against HTF bias

### Correlation Filter
**What it does**
- Avoids overexposure to similar assets.

**How it works**
- Compute correlation matrix
- If correlation > threshold:
  - keep highest-score signal
  - discard others

## 5) Signal Scoring & Risk Management

### Signal Scoring
**What it does**
- Assigns confidence score (0–100).

**How it works**
- Weighted factors:
  - strategy agreement
  - regime match
  - R:R ratio
  - HTF alignment
  - volatility sanity

### Risk Engine
**What it does**
- Defines SL/TP and risk %.

**How it works**
- ATR-based stop
- Dynamic position risk (0.5–2%)
- Multi-level take profits
- Calculates R-multiples

## 6) Signal Dispatch & Notifications

### Signal Dispatch
**What it does**
- Sends signals to users.

**How it works**
- Routes via Telegram notifier
- Tier formatting:
  - Free: summary
  - Premium: full details
  - VIP: elite-only signals
- Saves signal to DB before sending

### Alert Management
**What it does**
- Controls when users receive notifications.

**How it works**
- User-defined quiet hours
- Tier-based alert priority
- Redis-based rate limiting

## 7) Outcome Tracking (Trust Engine)

### Outcome Monitoring
**What it does**
- Tracks open signals in real time.

**How it works**
- Monitor price via WS / REST
- Detect:
  - TP1 / TP2
  - Full TP
  - Stop Loss
  - Invalidation
- Record outcome to DB

### Outcome Notifications
**What it does**
- Notifies users when trades close.

**How it works**
- Premium/VIP: immediate detailed alerts
- Free: delayed summary
- Includes result, R-multiple, duration

## 8) Performance & Analytics

### Performance Tracking
**What it does**
- Tracks historical performance.

**How it works**
- Aggregate outcomes
- Compute win rate, average R, strategy performance, asset performance

### Auto Reports
**What it does**
- Sends daily/weekly/monthly reports.

**How it works**
- Scheduled tasks
- Tier-based detail
- Cached computations

## 9) Monetization & Payments

### Subscription Management
**What it does**
- Controls paid access.

**How it works**
- Paystack payment links
- Webhook verification
- DB subscription records
- Auto-expiry downgrade/expire

### Referral System
**What it does**
- Rewards growth.

**How it works**
- Unique referral links
- Tracks conversions
- Grants bonus premium days

## 10) Security & Reliability

### Kill Switch
**What it does**
- Pauses all signals instantly.

**How it works**
- Redis flag
- Checked before dispatch

### Rate Limiting
**What it does**
- Prevents abuse.

**How it works**
- Per-user command limits
- Redis counters

### Logging & Monitoring
**What it does**
- Tracks system health.

**How it works**
- Structured logs
- Metrics endpoint
- Admin alerts on failures

## 11) ML Extension (Future)

### Data Labeling
**What it does**
- Prepares ML training data.

**How it works**
- Store each signal outcome
- Store feature snapshot

### ML Scoring (Optional Plug-in)
**What it does**
- Enhances confidence score.

**How it works**
- Trained model outputs probability
- Used as additive weight (not override)
