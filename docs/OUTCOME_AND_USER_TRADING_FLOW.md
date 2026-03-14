# SignalRankAI — Outcome Tracking & User Trading Flow

## 1) End-to-end lifecycle overview

This document describes how a signal moves from generation to user delivery, MT5 execution, and final outcome notifications.

High-level flow:

1. **Engine generates candidate signals** from market data.
2. **Signals are scored and filtered** (quality + freshness + tier logic).
3. **Signals are delivered** to users by tier.
4. **Users execute manually** via Telegram MT5 button, or use configured execution routing mode.
5. **Realtime outcome tracker monitors live price** for TP/SL progression.
6. **Outcome notifications are sent** per tier and per TP progression.
7. **Outcome data is persisted** and used by ML training/retraining.

---

## 2) Signal generation and delivery pipeline

Core loop runs in the engine cycle and dispatches to Telegram.

- Engine cycle and batch completion logic: `engine/core.py`
- User delivery dispatcher: `signalrank_telegram/bot.py` (`dispatch_signals()`)

Important delivery controls:

- Tier limits and routing (FREE/PREMIUM/VIP/ADMIN/OWNER)
- User preference filtering (assets/timeframes/strategies)
- Freshness and stale-signal filtering
- Duplicate variant collapsing
- DB-backed dedupe (`signal_deliveries`) to prevent duplicate sends

FREE flow supports FOMO-triggered unlock mode:

- VIP TP1 outcomes can trigger immediate FREE unlock delivery.
- Legacy random/delayed queue can be bypassed when FOMO-only mode is enabled.

FREE signal visibility policy:

- FREE users can see: **Entry, Stop Loss, and TP1**.
- Remaining TP ladder levels are locked (`TP2/TP3`) with upgrade prompts.

---

## 3) MT5 trading flow (user side)

### 3.1 One-click MT5 execution from Telegram

User taps the ⚡ button on a signal card.

Main callback:

- `signalrank_telegram/bot.py` → `_mt5_trade_callback()`

Checks performed before execution:

1. Tier gate (`PREMIUM+` required)
2. User profile existence
3. Execution mode gate (`none` blocks execution)
4. Daily premium cap (for PREMIUM)
5. MT5 account linked
6. Slippage validation vs signal entry
7. Lot sizing from user settings
8. Daily drawdown safety guard (execution blocked when daily loss limit is hit)

Execution call:

- `services/mt5_client.py` → `execute_trade()`

Success path:

- Sends user confirmation with order ID and remaining daily capacity (PREMIUM).

Failure path:

- Sends explicit error/slippage/credential message.

### 3.2 Execution routing mode

User-level field on `users`:

- `execution_mode`: `none | manual | auto`
- `auto_signals_daily_limit`: integer cap (`-1` means unlimited)

Command:

- `/execution` in `signalrank_telegram/commands.py`

Examples:

- `/execution manual`
- `/execution none`
- `/execution auto 5`
- `/execution auto all`

---

## 4) Realtime outcome tracking (TP/SL progression)

Tracker module:

- `engine/realtime_outcome_tracker.py`

Scheduler startup:

- Started from bot post-init in `signalrank_telegram/bot.py`

What it does continuously:

1. Loads active/unresolved signals (including TP-progressing states).
2. Fetches live prices.
3. Evaluates hit state: `tp1`, `tp2`, `tp3`/`tp`, `sl`.
4. Persists outcome progression using DB upsert logic.
5. Sends notifications to recipients.

### 4.1 TP progression behavior

- TP hit detection now progresses forward only.
- Duplicate/regressive TP notifications are blocked.
- Partial TP progress is retained (not prematurely archived at TP1/TP2).
- Signals archive on terminal outcomes (`tp3`/`tp`/`sl`).

### 4.2 Risk-free trigger (50% to TP1)

A one-time risk-free update is triggered when price reaches halfway from entry to TP1.

Behavior:

- Move SL to breakeven (best effort)
- Send risk-free notification
- Deduped by cache key to avoid repeated alerts

### 4.3 Retrace warning near SL after TP progress

After at least one TP is hit, retrace warning triggers when price moves back into the final SL-danger zone.

Default zone is 20% from SL side of TP→SL distance (`TP_RETRACE_SL_ZONE_PCT=0.20`).

Short example:

- SL = 100, TP1 = 62
- Warning threshold ≈ `100 - (100-62)*0.20 = 92.4`

Optional ML gate can reduce noisy warnings.

---

## 5) Outcome notifications and recipient handling

Notification fanout uses delivery recipients for each signal.

Key logic:

- `signalrank_telegram/bot.py` → `send_outcome_notifications()`
- Tier formatting differences for FREE/PREMIUM/VIP
- Quiet-hours and alert-preference checks
- Mark outcome as notified to avoid duplicate sends

---

## 6) Data persistence and ML learning loop

### 6.1 Core runtime tables involved

- `signals`
- `outcomes`
- `signal_deliveries`
- `mt5_executions`
- `users`

### 6.2 Persistent historical ML archive

Table:

- `ml_past_training_data`

Purpose:

- Preserve historical labeled data across one-time reset events.
- Allow retraining on both archive + fresh post-reset outcomes.

Migration:

- `alembic/migrations/versions/0018_ml_past_training_data.py`

Training integration:

- `ml/retrain.py` (union live + archive datasets)
- `ml/train_model.py` (blend engineered rows from both sources)

---

## 7) One-time fresh-start deployment mode

For Railway test reset while preserving users + ML archive:

- `START_FRESH_KEEP_USERS_ON_BOOT=1`

Boot behavior:

1. Snapshot current signal/outcome data into `ml_past_training_data`.
2. Truncate operational tables.
3. Keep `users`, `ml_past_training_data`, and migration metadata.
4. Set one-time marker in runtime state so reset runs once.

---

## 8) Safety controls in current flow

- Global kill-switch respected in dispatch jobs.
- Tier gates and daily premium execution limits.
- Hard risk cap enforcement for VIP risk setting and lot calculations.
- Daily drawdown guard on paid execution paths.
- DB dedupe for signal deliveries.
- Outcome dedupe/progression guard.
- Retry-safe messaging wrappers for Telegram rate-limit handling.

---

## 9) Operational checklist (recommended)

Before deploy:

1. Run Alembic migrations.
2. Set required env vars (Telegram, DB, broker integrations).
3. If doing one-time reset, set `START_FRESH_KEEP_USERS_ON_BOOT=1`.
4. Deploy and verify startup logs.
5. Run smoke tests.
6. Remove/disable one-time reset flag after verification.

---

## 10) Known scope boundaries

This document reflects the currently implemented production flow in this repository.
If new risk controls/execution policies are added, update this file alongside code changes.
