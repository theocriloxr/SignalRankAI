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

## 2026-06-29 Score Saturation Follow-Up

The latest diagnostic concern was that `max_score` and `max_score_pre_threshold`
were consistently `100`, which made the scorer look suspiciously flat.

Root cause:

- `engine.scoring.score_signal(...)` previously applied several legitimate
  quality multipliers and then hard-clipped the final value with
  `min(score, 100.0)`.
- The engine and Telegram delivery helpers then selected the maximum value
  across primary and auxiliary score fields such as `score_composite`,
  `rank_score`, and `quality_score`.
- That fallback behavior was useful when the canonical `score` field was zero,
  but it also made any helper field equal to `100` inflate `max_score`.

Implemented:

- `score_signal(...)` now keeps:
  - `score_raw`: the pre-cap audit value.
  - `score_calibrated`: the post-calibration score.
  - `score_soft_capped`: whether the high-score compression path was used.
  - `score_components`: weighted component details for RR, volatility,
    confidence, and confluence.
- High raw scores are compressed with a configurable soft cap instead of being
  flattened to exactly `100`.
- Engine and Telegram score resolvers now prefer the calibrated primary score
  before falling back to auxiliary score aliases.

New env knobs:

```env
SCORE_SOFT_CAP_ENABLED=1
SCORE_SOFT_CAP_KNEE=95
SCORE_SOFT_CAP_CEILING=99.5
SCORE_SOFT_CAP_SCALE=50
```

Expected post-deploy behavior:

- `max_score_pre_threshold` may still be high, but should no longer pin at
  `100` for every strong candidate.
- `score_raw` can exceed `100`; that is intentional and useful for debugging.
- Delivery gating and pulse diagnostics should use the calibrated score spread.

Verification added:

```powershell
python -m pytest tests\test_score_calibration.py tests\test_production_quality_guard.py tests\test_admin_pulse_delivery_count.py -q
```

Result: `7 passed`.

## 2026-06-29 Production Behavior Follow-Up: Score, MT5, Tier Caps, Tradeability

Latest live symptoms:

- Engine logs still showed `max_score=100.0` and `max_score_pre_threshold=100.0`.
- VIP Telegram messages showed `Conviction Score: 100.0%`.
- MT5 link flow said the account was linked, then Trade on MT5 acted as if it was not linked.
- FREE delivery limits could be bypassed by alternate delivery branches.
- Several signals prioritized very high RR/ROI while exposing small accounts to excessive stop distance.

Implemented:

- Score display resolution now prefers `score_calibrated`, then `score`, then
  `score_final`.
- Legacy exact `score=100` is display-capped by default with
  `SCORE_DISPLAY_MAX=99.5`.
- The core score soft cap can no longer be accidentally disabled by
  `SCORE_SOFT_CAP_ENABLED=0`; exact hard `100` now requires the explicit
  override `SCORE_ALLOW_HARD_100=1`.
- Signal explanations now use real score components, confluence, confidence,
  volatility quality, and R/R instead of falling back to only
  `High-conviction setup`.
- Final production quality gate now prioritizes tradeability before ROI:
  - rejects excessive stop-loss distance by asset class
  - rejects unrealistic/chase-style RR above an asset-class maximum
- `record_signal_delivery(...)` now enforces tier daily caps centrally, so
  resend jobs, FREE FOMO unlocks, direct dispatch, fallback dispatch, and
  queue-based paths cannot bypass the cap.
- MT5 link state now distinguishes:
  - `linked`: encrypted credentials saved
  - `executable`: MetaApi returned an executable account ID
- `/mt5_link` no longer says instant execution is ready when only credentials
  were saved.
- Live execution mode now falls back to the actual MT5 credentials table when
  user preferences do not contain `default_mt5_account_id`.

New env knobs:

```env
SCORE_DISPLAY_MAX=99.5
SCORE_ALLOW_HARD_100=0
QUALITY_MAX_STOP_LOSS_PCT_FX=0.80
QUALITY_MAX_STOP_LOSS_PCT_CRYPTO=2.50
QUALITY_MAX_STOP_LOSS_PCT_STOCK=2.00
QUALITY_MAX_STOP_LOSS_PCT_COMMODITY=1.50
QUALITY_MAX_RR_FX=4.50
QUALITY_MAX_RR_CRYPTO=4.00
QUALITY_MAX_RR_STOCK=3.50
QUALITY_MAX_RR_COMMODITY=3.50
```

Expected post-deploy behavior:

- Telegram conviction should no longer display as exact `100.0%` unless
  `SCORE_DISPLAY_MAX` is explicitly raised.
- The USDJPY-style `1:7.8` signal should be rejected by the max-RR quality
  guard unless you deliberately loosen `QUALITY_MAX_RR_FX`.
- The AVAX-style `13-16%` stop-loss exposure should be rejected by the stop
  distance guard unless you deliberately loosen `QUALITY_MAX_STOP_LOSS_PCT_CRYPTO`.
- MT5 status should be interpreted as two-stage: credentials can be saved while
  execution remains disabled until MetaApi provisioning succeeds.
- FREE users should be capped by `TIER_DAILY_LIMITS["free"]` at the delivery
  reservation layer.

Verification added:

```powershell
python -m pytest tests\test_score_calibration.py tests\test_production_quality_guard.py tests\test_delivery_limit_guard.py tests\test_mt5_link_state_contract.py -q
```

Result: `12 passed`.

## 2026-06-29 Follow-Up: Active Signals, Leaderboard Proof, Score Logs

Latest live symptoms:

- A user could receive a signal, then `/signals` did not list all still-active
  received signals.
- `/leaderboard` ranked users even when every listed profile had poor win rate
  and negative Avg R.
- Engine cycle logs could still print `max_score=100.0` because the log line
  printed raw candidate values directly.

Implemented:

- `/signals` now uses the received/unresolved signal feed for FREE users too,
  with a 30-day lookback, instead of only showing signals sent since UTC
  midnight.
- Received/unresolved signal lookup no longer hides a signal just because
  `signals.expired` or `signals.archived` is stale. An outcome row is now the
  authority for whether a received signal is resolved.
- Engine cycle logs now split display and raw scores:
  - `max_score`
  - `max_score_pre_threshold`
  - `max_score_raw`
  - `max_score_raw_pre_threshold`
- Display score logs use `SCORE_DISPLAY_MAX` and should not pin at exact
  `100.0` unless `SCORE_ALLOW_HARD_100=1`.
- `/leaderboard` now requires positive, qualified performance before publishing
  entries. Defaults:
  - `LEADERBOARD_MIN_TRACKED_TRADES=5`
  - `LEADERBOARD_MIN_WIN_RATE=45`
  - `LEADERBOARD_MIN_AVG_R=0.05`
- When no entries qualify, the leaderboard sends an honest no-qualified-data
  message rather than ranking negative expectancy accounts.

Verification added:

```powershell
python -m pytest tests\test_signal_visibility_and_proof_quality.py tests\test_score_calibration.py tests\test_production_quality_guard.py tests\test_delivery_limit_guard.py tests\test_mt5_link_state_contract.py -q
```

Result: `16 passed`.

## 2026-06-29 Railway Log Follow-Up: Zero Scores / No Owner Signals

The latest Railway logs showed the main blocker:

- Postgres repeatedly returned `FATAL: sorry, too many clients already`.
- The async DB engine logged an unsafe Railway monolith pool: `pool_size=16 max_overflow=6`.
- Bot setup, ML training, realtime outcome tracking, shadow tracking, expiry, and threshold optimization all failed or retried while Postgres was exhausted.
- Binance pair discovery was unavailable in the deployed region, but fallback assets and some real OHLC candles were still fetched from other providers.
- US stock symbols were correctly skipped because the US market was closed at the logged UTC time.

This means the all-zero pulse / `generated_signals=0` / `max_score=0` symptom was not evidence of demo data. The deployed service was starved of DB connections during startup, which prevented stable bot setup, tracking, persistence, and delivery.

### Implemented in this follow-up

- Railway detection now recognizes the full set of Railway deployment markers:
  - `RAILWAY_SERVICE_NAME`
  - `RAILWAY_ENVIRONMENT`
  - `RAILWAY_ENVIRONMENT_NAME`
  - `RAILWAY_PROJECT_ID`
  - `RAILWAY_SERVICE_ID`
  - `RAILWAY_DEPLOYMENT_ID`
  - `RAILWAY_REPLICA_ID`
  - public/private Railway domain markers where relevant
- DB pool caps are now enforced on Railway even if `DB_POOL_DISABLE_RAILWAY_CAP=1` is present. Uncapped mode requires the second explicit override `DB_POOL_ALLOW_UNCAPPED_RAILWAY=1`.
- Expected Railway DB log after redeploy:

```text
[db] Railway pool cap applied requested_pool=16 requested_overflow=6 effective_pool=2 effective_overflow=0
[db] async engine initialised ... pool_size=2 max_overflow=0
```

- If the deployed log still shows `pool_size=16 max_overflow=6`, the running service is on an old build or has deliberately enabled uncapped mode.
- Engine startup is delayed by default on Railway with `ENGINE_START_DELAY_SECONDS=12`.
- Worker startup is delayed by default on Railway with `WORKER_START_DELAY_SECONDS=20`.
- Worker sub-tasks are staggered by default on Railway with `WORKER_TASK_START_STAGGER_SECONDS=3`.
- Worker task restarts now use backoff instead of immediate restart loops.
- DB-related worker crashes use a longer default restart base on Railway.
- ML training is delayed on Railway with `ML_TRAIN_STARTUP_DELAY_SECONDS=300` when it is explicitly enabled.
- Drift monitoring is delayed on Railway with `ML_DRIFT_STARTUP_DELAY_SECONDS=180`.
- The shadow outcome tracker is now supervised correctly. Previously the worker supervised `shadow_outcome_worker.start()`, which returned immediately after spawning its internal task and caused repeated restarts.
- The Telegram APScheduler SQLAlchemy job store now defaults to MemoryJobStore on Railway to save a synchronous Postgres connection. Persistent scheduler storage can be restored with `BOT_SCHEDULER_PERSISTENT_JOBSTORE_ENABLED=1` after DB capacity is proven.
- Engine cycle logging now includes zero-signal reason counters:
  - `no_candles`
  - `stale_data`
  - `no_strategy_signals`
  - `validation_failed`
  - `risk_failed`
  - `advanced_filter_failed`
  - `invalid_tp`
  - `score_rejected`

### Recommended Railway env after this fix

Remove or lower any broad pool settings such as:

```env
DB_POOL_SIZE=16
DB_MAX_OVERFLOW=6
```

Use these safer monolith settings:

```env
DB_POOL_SIZE_RAILWAY=2
DB_MAX_OVERFLOW_RAILWAY=0
BOT_SCHEDULER_PERSISTENT_JOBSTORE_ENABLED=0
ENGINE_START_DELAY_SECONDS=12
WORKER_START_DELAY_SECONDS=20
WORKER_TASK_START_STAGGER_SECONDS=3
WORKER_TASK_DB_RESTART_BASE_SECONDS=60
ML_TRAIN_STARTUP_DELAY_SECONDS=300
ML_DRIFT_STARTUP_DELAY_SECONDS=180
```

If Postgres is still connection-limited, keep `ML_TRAIN_ENABLED=0` until the live evidence run shows stable DB health. The model can be trained as a separate one-off job or re-enabled after the monolith is stable.

### Post-redeploy acceptance checks

1. The boot log must show `pool_size=2 max_overflow=0`, not `16/6`.
2. The bot setup error `too many clients already` must disappear.
3. The shadow outcome tracker must not be restarted every second.
4. The first Engine Pulse may still be quiet during startup delay, but later cycles must show DB/runtime evidence.
5. If `generated_signals=0` persists, read the new engine counters to identify whether the bottleneck is provider candles, strategy generation, validation, risk, TP structure, advanced filters, or score thresholding.

## 2026-06-29 Full Log Follow-Up: Final Candidates Failed Storage

The full Railway logs showed the next bottleneck after scoring was fixed:

```text
generated_signals=0 max_score=88.87 max_score_pre_threshold=88.87
strategy_signals=143 ... final_signals=8 stored=0 ... store_failed=8
```

This means the strategy/scoring pipeline was alive and producing final candidates. The delivery path stayed silent because every final candidate failed at signal storage. No Telegram delivery can happen until a signal row is stored and receives a `signal_id`.

### Implemented in this follow-up

- Active-trade dedup now validates Redis active-trade entries against Postgres before blocking storage.
- If Redis points to a real unresolved DB signal, the existing signal is reused and duplicate storage remains blocked.
- If Redis points to a missing, closed, archived, or expired signal, the stale Redis active-trade entry is removed and the new candidate is allowed to store.
- Orphan Redis active-trade entries without a usable DB-backed signal ID no longer silently starve storage by default.
- `store_signal_compat(...)` now logs the block reason, asset, timeframe, direction, and signal ID when a dedup block still happens.
- Railway DB pooling now also detects Railway from DB URLs containing `railway`, not only Railway-specific env names.
- Added absolute Railway pool caps so accidental env values like `DB_POOL_SIZE_RAILWAY=16` cannot undo the safety cap:
  - `DB_POOL_RAILWAY_ABSOLUTE_CAP=2`
  - `DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP=0`

### Expected post-deploy cycle

After redeploy, the engine cycle should move from:

```text
final_signals=8 stored=0 store_failed=8
```

to at least some stored candidates, for example:

```text
final_signals=8 stored=3 store_failed=0 generated_signals=3
```

If storage is still blocked, the logs should now include a specific line like:

```text
[store_signal] blocked reason=active_trade asset=... timeframe=... direction=... signal_id=...
```

That line is the next diagnostic hook.

## 2026-06-29 Inline Keyboard Follow-Up

The latest Telegram screenshots showed signals reaching the owner, but the inline keyboard actions were not usable. The likely failure mode was Telegram rejecting oversized `callback_data` payloads, after which the send path fell back to a buttonless signal without logging the original failure.

### Implemented in this follow-up

- All live signal keyboards now use compact signal callback references capped for Telegram's 64-byte callback-data limit.
- `/signals` action keyboards now use the same callback contract as live signal delivery.
- The legacy utility signal keyboard no longer emits unsupported `reaction_...` callback names; it now uses:
  - `signal_reaction_<id>|taking_it`
  - `signal_reaction_<id>|watching`
  - `monitor_signal_<id>`
  - `check_outcome_<id>`
  - `mt5_trade_<id>`
- `open_signal_<id>` update buttons now use the same safe callback helper.
- A global callback-query fallback is now registered after concrete callback handlers, so unmatched buttons receive a controlled response instead of spinning indefinitely.
- The signal send fallback now logs:

```text
[send_signal] keyboard send failed chat_id=... user=... signal_id=... err=...
```

If this appears after deploy, the signal still sends, but the error text will identify why Telegram rejected the keyboard.

### Expected post-deploy Telegram behavior

Fresh signals should include working inline buttons:

- Taking It / Watching should update the reaction count and refresh the button row.
- Take Trade should either open the paid execution flow or show the correct tier/broker gate.
- Monitor should open or refresh a tracked monitor message.
- Check Outcome should show a popup with the stored signal status.

### Verification

Local verification passed:

```text
python -m py_compile signalrank_telegram\bot.py signalrank_telegram\commands.py signalrank_telegram\utils.py signalrank_telegram\callback_handlers.py db\pg_features.py db\pg_compat.py db\session.py engine\core.py
python -m pytest tests\test_callback_handler.py tests\test_command_contracts.py tests\test_command_tier_contract.py tests\test_signal_dedup_rules.py tests\test_monolith_hardening_defaults.py -q
python -m pytest tests\test_signal_deduplicator.py tests\test_realtime_outcome_tracker_user_perf_ids.py tests\test_broker_permission_validation.py tests\test_live_production_evidence.py -q
python scripts\production_readiness_check.py
```

Results:

```text
24 passed
12 passed
overall=PASS checks=8
```

## 2026-06-29 Quality, Stock Coverage, And Pulse Accuracy Follow-Up

Live owner reports showed:

- 30-day tracked win rate was 11.3% on sparse coverage.
- FX tracked outcomes were 0% wins in both FREE and VIP samples.
- Owner had not seen stock signals.
- Engine Pulse showed very high delivered counts while QA showed many reserved-but-not-confirmed rows.

### Implemented in this follow-up

- Added `PRODUCTION_QUALITY_GUARD_ENABLED=1` behavior by default at the final engine gate.
- Added asset-class-specific production quality defaults:
  - FX: score >= 94, RR >= 2.20, ML probability >= 0.68 when ML is present, ADX >= 25 when ADX is present.
  - Crypto: score >= 90, RR >= 2.00, ML probability >= 0.62 when ML is present, ADX >= 22 when ADX is present.
  - Stock: score >= 88, RR >= 1.80, ML probability >= 0.60 when ML is present, ADX >= 20 when ADX is present.
  - Commodity: score >= 90, RR >= 2.00, ML probability >= 0.62 when ML is present, ADX >= 22 when ADX is present.
- Added an FX emergency clamp:
  - FX signals default to `1h,4h,1d` only via `QUALITY_FX_ALLOWED_TIMEFRAMES`.
  - FX signals require 4h/1d MTF trend alignment by default via `QUALITY_FX_REQUIRE_MTF_ALIGNMENT=1`.
- Added per-class cycle diagnostics:
  - `selected_stock_assets`
  - `no_candles_stock`
  - `quality_rejected_stock`
  - equivalent crypto/fx/commodity counters
- Added open-universe logging:

```text
[engine] open universe by class: crypto=... fx=... stock=... commodity=... stocks_enabled=True
```

If stocks are empty while enabled, the engine now logs a warning pointing at market hours, `STOCK_TICKERS`, and stock OHLC provider keys.

- Removed the incorrect engine increment that counted a stored signal as delivered before Telegram send confirmation.
- Engine Pulse DB delivery count now only counts `signal_deliveries.sent_ok IS TRUE`.
- Successful Telegram dispatch paths now increment in-process delivered stats only after delivery confirmation is marked.
- `/qa_report` now splits unconfirmed rows:
  - pending
  - failed
  - stale
- Outcome backfill default increased to 2,500 delivered-untracked signals per tracker pass to improve sparse outcome coverage.
- Fixed a latent `math` import bug used by `_signal_display_score`.

### Tunable environment knobs

```env
PRODUCTION_QUALITY_GUARD_ENABLED=1
QUALITY_MIN_SCORE_FX=94
QUALITY_MIN_RR_FX=2.20
QUALITY_MIN_ML_PROB_FX=0.68
QUALITY_MIN_ADX_FX=25
QUALITY_FX_ALLOWED_TIMEFRAMES=1h,4h,1d
QUALITY_FX_REQUIRE_MTF_ALIGNMENT=1

QUALITY_MIN_SCORE_CRYPTO=90
QUALITY_MIN_RR_CRYPTO=2.00
QUALITY_MIN_SCORE_STOCK=88
QUALITY_MIN_RR_STOCK=1.80
QUALITY_MIN_SCORE_COMMODITY=90
QUALITY_MIN_RR_COMMODITY=2.00

OUTCOME_BACKFILL_SIGNAL_LIMIT=2500
```

### Expected post-deploy behavior

- Delivered counts in Engine Pulse should drop to confirmed sends only.
- Signal volume should drop materially, especially FX.
- FX signals should be rarer and only pass when score/RR/trend alignment are strong.
- Stock diagnostics should show whether stock tickers are entering the cycle, failing candles, or failing quality.
- `/qa_report` should make clear whether unconfirmed rows are pending, failed, or stale.
- Outcome coverage should improve over time as the backfill worker processes the backlog.

### Verification

Local verification passed:

```text
python -m py_compile engine\core.py engine\admin_pulse.py engine\realtime_outcome_tracker.py signalrank_telegram\bot.py signalrank_telegram\owner_commands.py
python -m pytest tests\test_production_quality_guard.py tests\test_admin_pulse_delivery_count.py tests\test_callback_handler.py tests\test_signal_dedup_rules.py tests\test_monolith_hardening_defaults.py -q
python -m pytest tests\test_deploy_log_regressions.py tests\test_realtime_outcome_tracker_user_perf_ids.py tests\test_live_production_evidence.py tests\test_command_contracts.py tests\test_command_tier_contract.py -q
python scripts\production_readiness_check.py
```

Results:

```text
19 passed
21 passed
overall=PASS checks=8
```

## 2026-06-30 follow-up: indices, active signals, dedupe, and outcome load

- Added first-class index support across discovery, classification, market-hours, candle routing, price routing, risk profiles, quality gates, stale validation, ML feature encoding, and engine class diagnostics.
- New index env knobs:
  - `INDICES_ENABLED=1`
  - `INDEX_TIMEFRAMES=1h,4h,1d`
  - `INDEX_TICKERS=US500,US100,US30,GER40,UK100,JPN225,VIX`
  - `INDEX_MARKET_MODE=cfd` or `cash`
  - `INDEX_DAILY_BREAK_UTC=21:00-22:00`
  - `TRADINGVIEW_INDEX_PREFIX=TVC`
- `/signals` now treats TP1/TP2/breakeven/progress outcomes as still active and falls back to `active_signal_messages` when Railway DB pressure delays delivery bookkeeping.
- Owner/admin delivery now bypasses daily caps but no longer bypasses signal dedupe by default. Set `OWNER_ADMIN_BYPASS_DELIVERY_DEDUPE=1` only for deliberate audit spam.
- Outcome tracker defaults are lighter for Railway monolith mode:
  - `OUTCOME_BACKFILL_SIGNAL_LIMIT` defaults to `100` instead of bulk 2500-style processing.
  - `OUTCOME_TRACKER_MAX_CONCURRENCY` defaults to `2`.
  - `OUTCOME_TRACKER_UPDATE_USER_PERF=0` by default; performance commands still calculate on demand.
- Outcome R-multiple is now signed and based on stop distance, not absolute movement divided by entry price. This prevents loss rows from poisoning ML/leaderboards as positive-R wins.
- Stop-loss notifications now label planned risk separately from actual market move/slippage at close.
- Production quality guard now blocks low-confluence signals when confluence metadata is present. Default minimums:
  - FX/crypto/indices/commodities/other: `QUALITY_MIN_CONFLUENCE_* = 50`
  - Stocks: `QUALITY_MIN_CONFLUENCE_STOCK = 45`

Expected post-deploy checks:

```text
[engine] open universe by class: ... index=...
[data] index_provider=... symbol=US500 mapped=^GSPC ...
[engine] ... selected_index_assets=... no_candles_index=... quality_rejected_index=...
```

If `/signals` still returns empty immediately after receiving a signal, check whether `active_signal_messages` rows are being created and whether `signal_deliveries` inserts are timing out.

## 2026-06-30 follow-up: duplicate exposure, tier caps, AI review visibility, and TP metadata

Live Railway/Telegram evidence showed repeated same-asset signals, partial-TP trades being treated as resolved, failed/reserved sends consuming daily quota, `Go to signal` buttons that did not jump to the edited message, and TP notifications with missing symbol/ref fields.

Changes made:

- `TIER_DAILY_LIMITS` now default to the product rules requested for launch:
  - free: `FREE_SIGNAL_DAILY_LIMIT=3`
  - premium: `PREMIUM_SIGNAL_DAILY_LIMIT=15`
  - VIP: `VIP_SIGNAL_DAILY_LIMIT=30`
  - owner/admin: `OWNER_SIGNAL_DAILY_LIMIT=100`, `ADMIN_SIGNAL_DAILY_LIMIT=100`
- Delivery cap counters now count only `signal_deliveries.sent_ok IS TRUE`, so failed Telegram attempts and stale reservations do not consume the user-visible daily allowance.
- Same-asset/same-direction delivery dedupe no longer treats `tp1`, `tp2`, breakeven, or partial progress as terminal. Default unresolved duplicate block is now `DELIVERY_UNRESOLVED_BLOCK_HOURS=168`.
- Updated-signal jump buttons now use a Telegram message URL generated by `_build_signal_message_link(...)` instead of a callback-only button.
- TP notification payloads are normalized before formatting, and the TP formatter now falls back across `asset`/`symbol`, `take_profit`/`targets`, and `signal_id`/`id`.
- Outcome tracker default lookback/backfill windows now default to 168 hours instead of 720 hours to reduce old backfill noise on Railway monolith deployments.
- Gemini review scores are now displayed in paid/admin signal formatting when present, and `_production_quality_gate(...)` blocks signals with numeric Gemini review scores below `QUALITY_MIN_GEMINI_SCORE_*` defaults of `8.0`.
- Paystack webhook processing now has a self-contained duration fallback so replayed `charge.success` events without `duration_days` do not crash when the optional legacy `paystack.paystack` package path is unavailable.

Recommended post-deploy checks:

```text
FREE_SIGNAL_DAILY_LIMIT=3
PREMIUM_SIGNAL_DAILY_LIMIT=15
VIP_SIGNAL_DAILY_LIMIT=30
OWNER_SIGNAL_DAILY_LIMIT=100
ADMIN_SIGNAL_DAILY_LIMIT=100
DELIVERY_UNRESOLVED_BLOCK_HOURS=168
QUALITY_MIN_GEMINI_SCORE_FX=8.0
QUALITY_MIN_GEMINI_SCORE_CRYPTO=8.0
ACTIVE_SIGNAL_LOOKBACK_HOURS=168
OUTCOME_BACKFILL_LOOKBACK_HOURS=168
```

Evidence to watch:

- Repeated USDJPY/AUDUSD/USDCAD style signals should update the existing message or be blocked while the prior same-direction exposure is unresolved.
- `/qa_report` delivered counts should align more closely with actual sent messages, not reservations.
- TP notifications should no longer show `None` or `Ref: N/A`.
- Signal messages should show `AI Review: Gemini x.x/10` when Gemini returned a review score.

## 2026-06-30 follow-up: 12-hour asset lock, executable MT5, faster setups, and AI fallback

Latest Railway/Telegram evidence showed:

- Duplicate same-asset deliveries inside 12 hours, including exact duplicate XAGUSD messages.
- Signals with an active same-asset exposure still being delivered.
- MT5 credentials saved but the trade button failing because no executable MetaApi account ID existed.
- Signals skewing toward slow 4h/1d target ladders with very high displayed R:R.
- Gemini configured but signal-level AI review not visible when Gemini failed or returned unparseable prose.
- Railway background `MarketMonitor` crashing on offset-naive vs offset-aware datetime subtraction.
- The attached `railway_dump.bak` is a PostgreSQL custom-format dump (`PGDMP`), but local `pg_restore` tooling was unavailable in this environment, so it was identified safely but not restored locally.

Changes made:

- Central delivery reservation now enforces a same-user/same-asset cooldown of at least 12 hours, regardless of direction, tier, or timeframe.
- Unresolved same-asset exposure remains blocked by `DELIVERY_UNRESOLVED_BLOCK_HOURS` even beyond the 12-hour cooldown.
- In-flight delivery reservations now block concurrent duplicate sends for `DELIVERY_INFLIGHT_RETRY_SECONDS=300` unless a previous send attempt recorded an error.
- `ASSET_REPEAT_LOCK_HOURS` and `TIER_ASSET_COOLDOWN_HOURS` defaults are aligned to 12 hours for all tiers.
- Signal analysis defaults now include `1m,5m,15m,1h,4h,24h`; `24h` normalizes to `1d`.
- Production quality gating now caps the largest available R:R value, including displayed `risk_reward` and full TP ladder distance, so 1:6+ to 1:11 ladders can no longer slip through by presenting a smaller pre-threshold R:R.
- Gemini review now has a deterministic local AI fallback using score, ML probability, confluence, stop distance, target realism, timeframe, and candle depth. Formatter labels it as `Local AI` rather than pretending it came from Gemini.
- MT5 trade execution now calls `ensure_user_mt5_account_id(...)`, which attempts to reprovision MetaApi from encrypted saved credentials before failing.
- `/mt5_status` now distinguishes saved credentials from an executable bridge with `Execution bridge: READY/NOT READY`.
- Market no-trade alert rate limiting now handles timezone-aware timestamps.

Recommended Railway env defaults after this pass:

```text
DELIVERY_SAME_ASSET_COOLDOWN_HOURS=12
ASSET_REPEAT_LOCK_HOURS=12
DELIVERY_INFLIGHT_RETRY_SECONDS=300
DELIVERY_UNRESOLVED_BLOCK_HOURS=168
CRYPTO_TIMEFRAMES=1m,5m,15m,1h,4h,24h
FX_TIMEFRAMES=1m,5m,15m,1h,4h,24h
STOCK_TIMEFRAMES=1m,5m,15m,1h,4h,24h
COMMODITY_TIMEFRAMES=1m,5m,15m,1h,4h,24h
INDEX_TIMEFRAMES=1m,5m,15m,1h,4h,24h
AI_REVIEW_FALLBACK_ENABLED=1
QUALITY_MIN_LOCAL_AI_SCORE=8.0
```

## 2026-07-01 follow-up: opposite-direction asset lock, segment quarantine, and Codex governance

Latest Telegram evidence showed `USDCAD` delivered as `BUY` and then `SELL` within minutes on different timeframes. Root cause:

- Engine storage cooldown was asset+timeframe scoped, so `USDCAD 1d` and `USDCAD 15m` were treated as different active exposures.
- Delivery locks counted only `sent_ok IS TRUE`, so a fresh in-flight reservation could fail to protect the user before Telegram send confirmation was written.

Changes made:

- Engine now has cycle-level asset cooldown in addition to asset+timeframe cooldown. Only one signal per asset can be stored in a cycle, regardless of direction or timeframe.
- Engine DB cooldown now also loads active assets from the last `ASSET_REPEAT_LOCK_HOURS` hours, defaulting to 12, so different-timeframe same-asset signals are blocked before storage.
- Central delivery reservation treats in-flight rows (`sent_ok=false` and `last_error IS NULL`) as locks. A second same-asset signal cannot slip through while the first send is still being confirmed.
- Delivery dedupe now fails closed when its safety query errors instead of falling back to same-signal-id uniqueness only.
- Free/random and extra-signal selection now exclude assets the user received or reserved inside the asset lock window.
- Segment auto-quarantine is enabled by default. Segments with at least `SEGMENT_QUARANTINE_MIN_TRADES=10` terminal outcomes in the lookback and win rate below `SEGMENT_QUARANTINE_MIN_WIN_RATE=45` or average R below `SEGMENT_QUARANTINE_MIN_AVG_R=0` are blocked.
- `/codex_audit` remains admin/owner-gated and now supports local evidence review plus optional OpenAI aggregate-only review. External review sends only grouped metrics and never sends Telegram IDs, user IDs, signal IDs, MT5 credentials, or raw database rows.
- `scripts/analyze_railway_sql_dump.py` can audit exported Railway SQL dumps for same-user/same-asset duplicates, score saturation, outcome distribution, active-message counts, and redacted MT5 linkage status.

Required/recommended Railway env:

```text
ASSET_REPEAT_LOCK_HOURS=12
DELIVERY_SAME_ASSET_COOLDOWN_HOURS=12
DELIVERY_UNRESOLVED_BLOCK_HOURS=168
DELIVERY_INFLIGHT_RETRY_SECONDS=300
SEGMENT_QUARANTINE_ENABLED=1
SEGMENT_QUARANTINE_LOOKBACK_DAYS=30
SEGMENT_QUARANTINE_MIN_TRADES=10
SEGMENT_QUARANTINE_MIN_WIN_RATE=45
SEGMENT_QUARANTINE_MIN_AVG_R=0
OPENAI_CODEX_REVIEW_ENABLED=1
OPENAI_API_KEY=<set in Railway>
OPENAI_CODEX_REVIEW_MODEL=gpt-4.1-mini
```

Post-deploy evidence to watch:

- Engine logs should show `skipped_cycle_asset_cooldown` or `skipped_db_asset_cooldown` for repeated USDCAD/AAVE/CADJPY-style candidates.
- Delivery logs should show `[dedup] Asset gate hit` before any second same-asset send reaches Telegram.
- `/codex_audit weekly` should report `External aggregate AI: ran` when OpenAI env vars are configured, otherwise `off/failed`.

## 2026-07-01 follow-up: Asset Position Manager and score saturation controls

The next hardening pass moved same-asset protection toward a central position-state model rather than scattered dedupe checks.

Changes made:

- Added `services/asset_position_manager.py` as the shared user/asset state resolver. It normalizes delivered/reserved rows and outcomes into `NONE`, `ACTIVE`, `TP1`, `TP2`, `TP3`, `STOPPED`, `EXPIRED`, and `CANCELLED`.
- `record_signal_delivery(...)` now queries the Asset Position Manager before using legacy fallback checks.
- Telegram pre-send asset locks now query the same Asset Position Manager.
- `_signal_display_score(...)` now prefers `score_calibrated` over raw `score` and caps uncalibrated perfect scores to `SCORE_DISPLAY_MAX=99.5` unless `SCORE_ALLOW_HARD_100=1`.
- Engine storage now writes the resolved capped score back into the signal payload before persistence, reducing future `score=100` accumulation.
- `/codex_audit` governance context now includes score saturation and outcome-integrity metrics so it can flag exact-100 score clusters, duplicate outcome rows, and suspicious absence of TP1/TP2 progress rows.

Additional recommended Railway env:

```text
SCORE_SOFT_CAP_ENABLED=1
SCORE_DISPLAY_MAX=99.5
SCORE_ALLOW_HARD_100=0
OUTCOME_IDEMPOTENCY_ENABLED=1
TELEGRAM_IDEMPOTENCY_ENABLED=1
MT5_IDEMPOTENCY_ENABLED=1
OBSERVABILITY_METRICS_ENABLED=1
EXECUTION_ELIGIBILITY_ENABLED=1
AI_CONSENSUS_MIN=0.85
AI_DISAGREEMENT_MAX=0.20
NEWS_BLACKOUT_MINUTES=30
PROVIDER_FAILOVER_ENABLED=1
PROVIDER_MAX_ERRORS=5
PROVIDER_COOLDOWN_SECONDS=300
```

## 2026-07-01 follow-up: trader profiles, command reliability, and DB pressure

This follow-up converts SignalRankAI from a single swing-biased signal stream into a profile-aware trading system. The engine now annotates each signal with a trader profile (`scalp`, `day`, `swing`, or `position`), profile-specific expected hold time, expiry, and target model. Telegram users can select a preferred profile with `/profile`; dispatch filters signals to that profile before delivery.

Changes made:

- Added `services/trade_profiles.py` for profile normalization, ATR-based TP/SL shaping, expected time-to-target scoring, user profile persistence, and profile delivery matching.
- Added `services/trading_ledger.py` as the first event-ledger layer for generated signals and guarded state transitions.
- Added `/profile` and owner-only `/db_health` Telegram commands, plus matching command-access/help entries.
- Hardened the Telegram command audit wrapper with command timeouts, error references, and DB-pressure logging so “too many clients” failures become diagnosable instead of silent UX failures.
- Added database pool diagnostics and Postgres activity snapshots for Railway monolith operations.
- Updated signal formatting so premium/VIP users see the signal style and expected hold.
- Updated `/signal all` behavior to direct users to `/signals` instead of looking up a fake reference.
- Fixed long-running owner actions so `/force_market_scan` acknowledges immediately and broadcast/terms blasts no longer report success when zero users received the message.
- Hardened `TierDeliveryManager.get_users_for_signal(...)` so it no longer creates an unmanaged async DB session from synchronous code; callers must pass a sync session or use the managed helper that closes its session.

Additional recommended Railway env:

```text
TRADE_PROFILE_ENGINE_ENABLED=1
TRADING_LEDGER_ENABLED=1
COMMAND_HANDLER_TIMEOUT_SECONDS=60
DB_POOL_PRE_PING=true
DB_USE_NULLPOOL=false
DB_POOL_SIZE_RAILWAY=2
DB_MAX_OVERFLOW_RAILWAY=0
```

Remaining live evidence still required:

- Railway `/db_health` output during peak command traffic.
- Real provider availability under the production asset universe.
- MT5/Binance/Bybit sandbox execution proof with broker-side order IDs.
- Outcome coverage recovery proof after the active-signal and expiry fixes are deployed.

External implementation notes checked during this pass:

- TradingView webhooks send alert payloads to user-provided HTTP endpoints, require secure handling, support JSON bodies when the alert message is valid JSON, and cancel requests taking longer than three seconds. SignalRankAI should keep webhook handlers fast, authenticated, and non-blocking.
- MT5 `order_send` requires a structured trade request and broker-side validation of symbol, volume, price, SL, TP, order type, filling type, expiration, and retcode handling. SignalRankAI broker execution should continue to fail with structured reasons before and after broker submission.
- Binance symbol filters such as price, lot size, and notional constraints require pre-trade normalization before order placement.
- Bybit order creation requires category/symbol/side/order type/quantity inputs and exchange-specific validation; execution adapters should normalize broker payloads but preserve provider-specific rejection codes.
