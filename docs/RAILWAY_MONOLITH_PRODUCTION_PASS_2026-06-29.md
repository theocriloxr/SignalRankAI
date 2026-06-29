# Railway Monolith Production Pass - 2026-06-29

## Scope

This pass focused on the Railway monolith symptoms reported from production logs:

- Owner received no signals after deployment.
- Engine Pulse showed all-zero counters.
- `max_score` could appear as zero.
- QA coverage was extremely low: 3250 delivered, only 24 tracked outcomes.
- `/help` command coverage needed proof.
- Copy trading, paper trading, auto trading, and MT5 routing needed production hardening.
- Signal deduplication needed stronger duplicate suppression without demo data.

## Implemented / Verified

### Owner/admin delivery

- Owner/admin delivery tiers are preserved as privileged tiers instead of being collapsed into ordinary VIP gating.
- Owner/admin delivery display still uses VIP formatting where appropriate.
- Owner/admin monitoring deliveries bypass per-asset delivery cooldowns while exact duplicate delivery rows remain protected.
- Engine-side duplicate filtering resolves internal `users.id` before querying `signal_deliveries.user_id`, avoiding Telegram-ID/internal-ID mismatch.

### Score handling and `max_score`

- Delivery and engine ranking use a canonical score resolver that accepts `score`, `_preview_score`, `score_total`, `score_composite`, `composite_score`, `rank_score`, and `quality_score`.
- Stored signals preserve the resolved score when the canonical `score` field would otherwise be zero.
- Eligibility logging now reports the resolved delivery score, reducing false `max_score=0` diagnostics.

### Delivery tracking / QA integrity

- Telegram dispatch now marks reserved deliveries as `sent_ok=True` only after successful send/update.
- Failed Telegram sends and false returns are marked `sent_ok=False`.
- QA report now displays outcome coverage and unconfirmed reservations:
  - `Delivered`
  - `tracked`
  - `coverage`
  - `Reserved but not confirmed sent`
- QA report warns when tracked coverage is too sparse for a reliable expected win-rate estimate.

### Engine Pulse

- Engine Pulse merges runtime counters with DB evidence from decisions, signals, and deliveries.
- Pulse uses `delivered_at` for `signal_deliveries`, with `created_at` fallback for older schemas.
- Added `ENGINE_PULSE_INITIAL_DELAY_SECONDS` (default `300`) so Railway cold starts do not immediately send a misleading all-zero pulse.
- Pulse now adds a cold-start note when neither runtime stats nor DB evidence exists in the window.

### Paper trading

- Fixed TP/SL detection for long and short paper positions:
  - Long SL now triggers when price is below/equal stop.
  - Short SL now triggers when price is above/equal stop.
  - TP parsing supports scalar, list, dict, and JSON string formats.
- Paper close lookup now uses the real `user_id` instead of scanning fake Redis buckets.
- Added `sync_execution(...)` so live MT5 fills can be mirrored into the paper ledger.

### Auto trading / copy trading / MT5 routing

- Execution mode aliases are normalized:
  - `copy` -> `copy_trade`
  - `none` -> `signals_only`
  - `paper` -> `semi_auto`
- `signals_only` never executes paper/live trades.
- `copy_trade` and `auto` route to live MT5 execution when the user has a linked account and premium+ tier.
- MT5 router validates hard stop-loss, take-profit, entry, direction, and stop direction before broker execution.
- MT5 auto execution has Redis idempotency via `broker_exec_once:{user_id}:{signal_id}`.
- Missing `sync_execution` was added so MT5 execution sync does not fail after broker fill.

### Binance/Bybit exchange broker linking

- Added authenticated exchange broker linking endpoints:
  - `POST /broker/exchange/link`
  - `GET /broker/exchange/status?provider=binance|binanceus|bybit`
- Supported providers:
  - Binance
  - Binance US
  - Bybit
- Exchange API keys must pass the same trade-only permission policy as the validator:
  - read required
  - trade required
  - withdraw disabled
  - internal transfer disabled
- Credentials are stored in Postgres `runtime_state` only after encryption.
- The endpoint refuses to link credentials unless `ENCRYPTION_KEY` is configured.
- Responses return only masked key metadata, never plaintext secrets.

### Outcome tracking

- Delivered-untracked outcome backfill now only includes `sent_ok=True` deliveries.
- Active and backfill caps are configurable and larger by default:
  - `OUTCOME_ACTIVE_SIGNAL_LIMIT=1000`
  - `OUTCOME_BACKFILL_SIGNAL_LIMIT=1000`
- This directly addresses the QA symptom where only 24 of 3250 delivered signals had tracked outcomes.

### Signal deduplication

- Added cross-timeframe thesis fingerprints:
  - exact fingerprint: asset + direction + entry bucket + timeframe
  - cross-timeframe fingerprint: asset + direction + entry bucket
- DB duplicate lookup can suppress same-thesis repeats across timeframes by default with `SIGNAL_DEDUP_CROSS_TIMEFRAME=1`.
- Set `SIGNAL_DEDUP_CROSS_TIMEFRAME=0` to return to exact-timeframe-only behavior.

### Command/help coverage

- Added regression coverage proving every command listed in paginated `/help` has a bot handler.
- The test recognizes both plain `CommandHandler(...)` registrations and `/connect_broker` registered through its `ConversationHandler`.

## Verification

Commands run from `C:\Users\sammm\Desktop\SignalRankAI1`:

```powershell
.\.venv\Scripts\python.exe -m py_compile engine\core.py signalrank_telegram\bot.py signalrank_telegram\owner_commands.py db\pg_features.py services\trading_mode_manager.py services\mt5_signal_router.py core\paper_ledger.py engine\signal_deduplicator.py engine\admin_pulse.py engine\realtime_outcome_tracker.py tests\test_command_tier_contract.py tests\test_paper_ledger_exits.py tests\test_execution_safety.py
```

Result: passed.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_command_tier_contract.py tests\test_paper_ledger_exits.py tests\test_execution_safety.py tests\test_signal_deduplicator.py tests\test_realtime_outcome_tracker_user_perf_ids.py -q
```

Result: `16 passed`.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_broker_permission_validation.py -q
```

Result: `5 passed`.

```powershell
.\.venv\Scripts\python.exe scripts\production_readiness_check.py
```

Result: `overall=PASS checks=8`.

## Real Data / Demo Data

The offline readiness checker confirms the fetcher contract declares real chart candles with no demo/synthetic generation. This is a source-level guarantee only. Live Railway validation still requires checking the deployed environment variables and provider health:

- `DATABASE_URL`
- `REDIS_URL` or `REDIS_PRIVATE_URL`
- `TELEGRAM_BOT_TOKEN`
- real provider keys for Polygon/TwelveData/AlphaVantage/Binance/Bybit/etc.
- broker credentials only through the broker-linking flow
- `ENCRYPTION_KEY` before `/broker/exchange/link` is enabled

## Current QA Win-Rate Interpretation

The pasted QA report implies:

- Delivered: `3250`
- Tracked outcomes: `24`
- Coverage: `0.74%`
- Tracked wins: `9`
- Tracked losses: `15`
- Observed tracked win rate: `37.5%`
- Crypto tracked win rate: `100.0%` on `9/9`
- FX tracked win rate: `0.0%` on `0/15`
- Commodities: pending outcomes

This is not enough coverage to estimate the true expected production win rate. The honest answer is:

- Current observed tracked win rate: `37.5%`
- Reliable expected win rate: not yet measurable from the pasted QA data
- Required before a real estimate: at least 80% outcome coverage and a statistically meaningful sample per asset class/tier

## Production Readiness Scorecard Status

The offline readiness checker passes, but the evidence-based `docs/PRODUCTION_READINESS_SCORECARD.md` still contains subsystem scores below 90. I did not inflate those numbers because the scorecard explicitly requires evidence before raising scores.

To honestly move every subsystem to 90+, the remaining evidence must come from live production validation:

1. Railway monolith smoke test with Postgres and Redis connected.
2. Telegram owner/admin/free/premium/VIP command and callback E2E test.
3. Provider health test with real candles across crypto, FX, commodities, and stocks.
4. MT5/paper/live/copy execution sandbox test with idempotency evidence.
5. Outcome tracking catch-up test showing QA coverage improving materially above the current 0.74%.
6. Payment/subscription webhook verification.
7. Observability check for health, metrics, alerts, and pulse counters after at least one full engine cycle.

## Railway Env Recommendations

Recommended production env values after this pass:

```env
ENGINE_PULSE_INITIAL_DELAY_SECONDS=300
OUTCOME_ACTIVE_SIGNAL_LIMIT=1000
OUTCOME_BACKFILL_SIGNAL_LIMIT=1000
SIGNAL_DEDUP_CROSS_TIMEFRAME=1
BROKER_EXEC_IDEMPOTENCY_SECONDS=86400
RISK_FREE_USER_COOLDOWN_SECONDS=43200
```

## Immediate Post-Deploy Checks

After redeploying on Railway:

1. Run `/myid` as owner and confirm the ID is in `OWNER_IDS`.
2. Run `/ops_health`, `/provider_status`, `/qa_report 30`, `/signals`, `/status`.
3. Wait one complete engine cycle before judging Engine Pulse.
4. Confirm Engine Pulse shows nonzero scanned/signals/deliveries after cycle completion.
5. Confirm `/qa_report 30` coverage rises as outcome backfill catches up.
6. Confirm owner receives signals even when free/VIP users are gated by limits.
