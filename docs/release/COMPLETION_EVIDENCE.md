## Current local continuation — 16 October 2026

## Continuation, 3 November 2026 (daily review) — missed entries keep no R, stuck account emails, shadow-tracker throughput (scheduled review session)

Commits `ae6e64a`, `9bb86c6`, `3ccd248` on `feat/frontend-rebuild-and-stage1-hardening` (parent `0652458`). Production evidence was read through the ops relay on 3 Nov 05:40–06:25 UTC (read-only SQL and log greps).

- **Missed entries booked as losses (`ae6e64a`).** The BCHUSDT `missed_entry` of 2 Nov (signal `a0ec7de7`) is stored with `r_multiple = -1` and `performance_inclusion_status = eligible`; in the last 120 days 32 eligible `missed_entry` outcomes carry an R (avg −1.84R, range −63R to +40R). A pending projection already held a provisional R and `upsert_outcome` keeps the old value when the terminal write passes `None`. `upsert_outcome` now clears `r_multiple`/`percent` for `missed_entry`, `missed` and `expired`; the strategy scorecard's issued source skips those statuses so the historical rows stop counting. The historical rows are not corrected in the database (owner decision; an audited correction is proposed in the daily report).
- **Account emails stuck in `sending` (`9bb86c6`).** `email_outbox` held a `magic_login` (2 Nov 12:48 UTC) and a `verify_email` (13:38) in `sending` for 16 h with no `sent_at`; nothing reclaimed a claimed row. Rows past `EMAIL_SENDING_LEASE_SECONDS` (default 300) are retried while their link is valid (`created_at + context.expires_minutes`, 2 min to spare) and failed with `sending_lease_expired` otherwise; a failed status update no longer aborts the batch. A re-send of a message that was sent but not recorded is possible once (at-least-once delivery).
- **Shadow-tracker throughput (`3ccd248`).** Analytics logs show 150-row batches every ~90 s (`processed=55–62 scanned=150`), because each row fetched its own candles. ML-layer rejections arrive at ~165k/day (37,992 rows 00:25–05:56). Correction to the commit message: the ML tracker is gaining, not falling behind — at 06:00 on 3 Nov its newest labelled row was created 2 Nov 15:09 (≈ 15 h behind, versus ≈ 35 h on 2 Nov), at 3.5–5k labels per hour; 35–45 % of each hour's labels were `unverifiable` until 05:00. The expectancy layer's 31 Oct backlog is old because that layer receives no new rows since `EXPECTANCY_HARD_BLOCK_ENABLED=0`. Candles are now fetched once per asset × timeframe per batch instead of per row, which shortens each batch; outcome rules are unchanged.
- No threshold, gate, scorecard mode or bound, kill switch, execution or billing setting changed.
- Tests (Linux, Python 3.11.18, venv from `requirements.txt`; not CI, staging or production): `tests/test_missed_entry_clears_projection_r_20261103.py` (5), `tests/test_email_outbox_sending_lease_20261103.py` (4, the reclaim SQL against a scratch PostgreSQL 16.15 via `SIGNALRANK_TEST_PG_DSN`), `tests/test_shadow_tracker_series_fetch_20261103.py` (3). The 48 outcome, email, shadow, scorecard, platform, identity, integrity and learning test files: 452 passed, 6 skipped (exit 0). Governance regenerated with `scripts/build_v7_governance.py` and `scripts/build_release_inventory.py`.

## Continuation, 2 November 2026 — evidence-based setup filter, ML advisory, protected exits, performance page (owner request)

Commits `e68eab8f`, `f117be00`, `cb2be103`, `78cca12b`, then `6bfc285b` and `6c357aa5` after the first production observation. The owner approved pushing them to `feat/frontend-rebuild-and-stage1-hardening` ("Yes, push and watch"); that branch deploys to the self-hosted production server.

- **The owner asked for an 82% win rate.** No filter can promise that, and none was set. The thresholds below come from the platform's own tracked results.
- **Setup-evidence filter (`services/segment_evidence.py`).** This replaces the segment quarantine, which never blocked anything.
  - A setup is a strategy × timeframe × direction. It may signal only while the Wilson lower bound of its TP1-or-better rate beats the break-even rate of the plan it publishes: `1 / (1 + f1 × rr_tp1)`.
  - The confidence level comes from `SEGMENT_EVIDENCE_CONFIDENCE` (default 0.95). `f1` is the published TP1 close fraction.
  - Evidence covers 60 days: shadow outcomes plus delivered outcomes. A rejected setup counts once per asset and bar, because the engine logs it again on every scan.
  - The worker stores a snapshot in `runtime_state` (`segment_evidence:v1`) every 15 minutes, and the engine reads only that snapshot. While the ML gate is advisory, a missing or stale snapshot blocks signals.
- **Read-only production replay (60 days, one setup per bar).** Allowed setups: 34,614, with 41.9% reaching TP1 and a +0.02R floor. Blocked setups: 70,567, with 31.2% reaching TP1 and −0.38R.
- **The ML gate is advisory (`ML_GATE_MODE`, default `advisory`).** The serving model scored pegged tokens above its 0.84 threshold and real coins below it.
  - The model still scores every signal, and a below-threshold score is logged as `ml_filter` with `ml_gate_mode=advisory`.
  - Such signals are marked paper-only: live broker execution is disabled for them, and the Telegram card says so. `ML_GATE_MODE=enforce` restores the veto.
- **Protected exits and observed prices (`e68eab8f`).**
  - After TP1, the outcome tracker treats entry as the active stop, so a stop recorded after TP1 is breakeven, not SL. This holds for hit checks, event prices and persisted outcomes.
  - Reconciliation records the observed price, and bot messages prefer it.
- **Web (`e68eab8f`).**
  - `/performance` counts closed trades by upper-cased bucket. Win rate is TP3 / (TP3 + SL), and the summary also shows partial wins, breakeven, open and not-triggered signals.
  - Signal cards show every target, reward/risk and price labels, and hide a missing probability.
- **Tests.** `tests/test_segment_evidence_20261102.py` (10, including real-PostgreSQL worker → snapshot → engine gate). The targeted suites passed: 72 tests across the segment evidence, pipeline, run_sync, Bybit, Telegram contract, endgame and v1366 files.
  - Full Python suite at `78cca12b`: 4506 passed, 1 failed, 2 skipped (FAIL (1 environmental: isolated python -I cannot import the user-site alembic; same as 43aa34e8)). Scope: Local Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to 0057; not CI, staging or production.
  - Frontend `tsc`, `eslint`, `test:transport` and `test:presentation`: exit 0.
- **After the push (`811dd794` served 2 Nov 23:12 UTC).**
  - The first evidence refreshes failed with `TimeoutError`. Production sets `DB_COMMAND_TIMEOUT=15`, and the 60-day aggregate takes 40 s (decision_log: 2.1M rows, 3.5 GB).
  - `6bfc285b` reads hourly windows instead. A read-only production timing of all 1,440 windows gave at most 4.0 s each and 139 s in total.
  - `6c357aa5`: the quality gate was re-applying an ML floor (`quality_recovery_ml`, raw ≥ 0.40) to advisory signals, which rejected 105 of 1,011 candidates in 45 minutes. Advisory signals now skip the ML floors only.
  - Both were served as `6c357aa5`. The worker logged `segment evidence refreshed segments=92`, and `/readyz` returned 200.
  - In the next 10 minutes, 174 candidates passed the advisory ML step and 0 were issued. All were rejected before the evidence filter, mostly by `production_quality:quality_score < 82` (crypto 80, commodity 31), plus EMA distance, weak trend and stop width.
  - Those floors are hand-set constants in `engine/core.py::_production_quality_gate`. They were left unchanged: lowering them to raise signal counts is excluded, and replacing them is an owner decision.
  - Per-strategy 60-day TP1 rates (one setup per bar): ATR Breakout 47.7% (2,694), MACD 38.1%, RSI 37.4%, ADX Trend 34.8% (18,123), EMA Trend 34.2% (80,751). No strategy with more than 41 setups exceeds 48%.

- **Score floors advisory (owner decision, 3 Nov: "Yes, make it advisory").**
  - On production the quality score carried no information about reaching TP1: AUC 0.489 over 6,190 tracked candidates (`docs/release/evidence/continuation-20261102/score_floor_test.json`).
  - With `QUALITY_SCORE_GATE_MODE` at its default `advisory`, the three score floors record `score_floor_advisory` on the signal instead of rejecting it. This holds only while the setup-evidence filter is enabled. The three floors are the production quality gate, the engine score gate and the canonical quality gate.
  - The evidence filter then decides, and it blocks when its snapshot is missing.
  - Live execution keeps the score floor, and it refuses any signal marked `score_floor_advisory`. The Telegram card says PAPER ONLY.
  - `enforce` restores the veto, as does disabling the evidence filter.
  - Stop width, reward/risk, confluence, AI and geometry checks are unchanged.
  - Full Python suite with the change: 4509 passed, 4 failed (first run; then the two production-quality tests were pinned to QUALITY_SCORE_GATE_MODE=enforce and extended to the advisory default (12 pass), governance regenerated; 1 environmental isolated-metadata failure remains).

- **Still open:**
  - corrupt historical R values in old outcomes;
  - `DEPLOYMENT_TELEGRAM_SEND_TEST=1` on the server (owner);
  - Paystack payment channels (owner, account level);
  - the email flows;
  - the empty-cycle pause and the `SignalController` ATR repair (owner decisions).

## Continuation, 2 November 2026 (daily review) — strategy scorecard counts one setup once per bar (scheduled review session)

- Production evidence (2 Nov, `decision_log` tracked rows 28–31 Oct): the engine re-logs the same rejected setup on every scan, so single cells were built from one or two bars repeated thousands of times — XAGUSD 4h EMA Trend 3,470 rows (94 % on 30 Oct, all stops), XAUUSD 15m EMA Trend 3,112 rows (100 % on 30 Oct), AAVEUSDT 1h EMA Trend 1,622 rows (92 % on one day). Each was penalised at the 0.85 floor from what is effectively one or two trades.
- `services/strategy_scorecard.py`: shadow rows count once per asset × timeframe × strategy × direction × timeframe bar (first logged row wins); issued outcomes are unchanged. The rebuild summary reports `duplicates_skipped`. Scorecard mode, bounds, sample minimums and edge margin are unchanged.
- Tests: `tests/test_strategy_scorecard_20261102.py` (+2) with the discovery and shadow-window tests, 35 pass locally (Python 3.11.18).

## Continuation, 2 November 2026 (daily review) — shadow outcomes no longer judged from a candle window that starts after the rejection (scheduled review session)

- Production evidence (2 Nov 05:48 UTC, `decision_log`): rows tracked in the previous 6 h were labelled on average 46 h after the rejection, while providers return 200 bars (`[data][async] ... tf=5m candles=200`), i.e. 3.3 h of 1m and 16.7 h of 5m history. Every 1m/5m row in that window was judged from candles that began long after the rejection, so the first barrier touch could be missing; their win rates (1m 47 %, 5m 31 % vs 1h 6 %) fed the scorecard and retraining.
- `engine/shadow_outcome_worker.py`: when the first returned candle opens more than one bar after the rejection, the row is stored as `unverifiable` (excluded by the trainer, scorecard, expectancy shadow and admin counts, which accept only tp*/sl/win/loss). Without candles, a live price may decide a row only within max(2 bars, 30 min) of the rejection; older rows wait for candles. No threshold, gate, scorecard mode or trading setting changed.
- Tests: `tests/test_shadow_tracker_history_window_20261102.py` (6) plus 195 shadow-tracker, expectancy, scorecard and ML-learning tests pass locally (Python 3.11.18; 2 skipped).

## Continuation, 2 November 2026 (afternoon) — Binance USDⓈ-M adapter, broker symbols, chart, new workspace (server session)

- Binance USDⓈ-M futures execution through the existing exchange router and reconciler, with exchange-side protective orders via the Algo Order API and an emergency close if protection fails; new default-off `BINANCE_EXECUTION_ENABLED` gate flag. MT4/MT5 broker symbol resolution (`services/broker_symbols.py`). Signal-detail price chart. BTC crash breaker scoped to crypto. Economic calendar includes next week. The website builds in `next` workspace mode with Telegram activation on the new sign-in page.
- Tests: `tests/test_binance_futures_client_20261102.py` (8), `tests/test_broker_symbols_20261102.py` (3), `tests/test_signal_chart_20261102.py` (2), `tests/test_calendar_next_week_20261102.py` (1) and 1,035 broker, gate, API and exchange tests pass locally (97 skipped); two historical source-contract assertions were updated for the intended Binance change. Frontend: `tsc`, `eslint`, transport (81) and presentation (41) tests and `next build` pass. No real-money permission changed.

## Continuation, 2 November 2026 (midday) — worst-case loss headroom and prop-firm presets (server session)

- Account policy evaluation adds worst-case daily/drawdown headroom over open-position risk, `max_allowed_risk_pct`, and an optional loss-streak pause. `core/prop_rules.py` adds sourced, dated presets for FTMO, FundedNext and Topstep programs and a `prop_preset` hard rule that keeps equity above both firm floors plus a buffer even if every open position and the new order stop out; the MT5 router supplies open-position risk. New routes `GET /broker/prop-presets` and `PUT /broker/connections/{id}/prop-preset` (parity matrix updated). Only restrictions were added; no permission, kill switch or live-trading setting changed.
- Tests: `tests/test_prop_rules_20261102.py` (14) plus 659 API, router, policy and parity tests pass locally (94 skipped). Notes: `docs/operations/SERVER_OPERATIONS_HANDOFF_20261101.md` §11.

## Continuation, 2 November 2026 (later morning) — trading styles, intraday and volume research, account-flipper profile (server session)

- Strategy discovery researches 5m/15m/1h/4h/1d once per trading style (scalp, day, swing, position, flip) with style-specific exits and time stops, adds three volume-confirmed rule families (skipped without real volume), and tags every spec and candidate with `trade_profile`.
- New `flip` trade profile (`/profile flip`, web profile update, paid tiers): explicit flip setups or 15m–4h setups with a ≥ 3R target. No risk-per-trade, sizing, execution or payout setting changed.
- Tests: `tests/test_strategy_discovery_20261102.py` (18) and 701 profile, tier, bot, strategy and engine tests pass locally (19 skipped). Notes: `docs/operations/SERVER_OPERATIONS_HANDOFF_20261101.md` §10.

## Continuation, 2 November 2026 (morning) — strategies discovered per asset from long external history (server session)

- `ml/strategy_discovery.py` backtests 360 rules per asset and timeframe on years of external history (Binance public data, Yahoo Finance; SignalRank candles as fallback) with costs, selects on the first 60 % of history, and keeps a rule only if it is profitable on both later windows. Weekly re-runs re-test and retire decayed specs; specs are approved or retired from their own forward-tracked record.
- `strategies/discovered.py` evaluates the published specs inside `run_all_strategies`; the default `DISCOVERED_STRATEGIES_MODE=shadow` only records them for forward tracking. `live` returns approved specs as ordinary candidates that pass every existing gate. No real-money or delivery setting changed.
- Tests: `tests/test_strategy_discovery_20261102.py` (11, incl. no survivors on a random walk) plus 214 strategy/engine/analytics tests pass locally. Operations notes: `docs/operations/SERVER_OPERATIONS_HANDOFF_20261101.md` §9.

## Continuation, 2 November 2026 — per-asset strategy scorecard and expectancy shadow tracking (server session)

- `services/strategy_scorecard.py` learns, per asset × timeframe × strategy × direction, from issued outcomes and from every shadow-tracked rejected setup, and publishes a scorecard to Redis every 3 h from the analytics role. The engine applies at most a 0.85–1.15 score multiplier, only when a cell has ≥ 40 outcomes and its Wilson 95 % win-rate interval clears the cell's own break-even win rate; `STRATEGY_SCORECARD_MODE` defaults to `shadow` (annotation only). It cannot create a signal or bypass a gate.
- `runtime/analytics.py` now also starts the expectancy-layer shadow tracker, which was registered only in the worker where production disables shadow tracking; 93k expectancy rows had never been followed forward.
- Production retrain with all rejected evidence (231,747 rows) was rejected by the quality gate (accuracy 0.69 vs majority baseline 0.82, expected R −0.17); the serving model was preserved.
- Tests: `tests/test_strategy_scorecard_20261102.py` (8) plus 536 existing engine/analytics/runtime tests pass locally. Operations notes: `docs/operations/SERVER_OPERATIONS_HANDOFF_20261101.md` §8.

## Continuation, 1 November 2026 (evening) — duplicate suppression no longer logged as a storage error (server session)

`db/pg_compat.store_signal_compat` logged `SignalDedupBlocked` (expected `min_interval` suppression) with a full traceback at ERROR, which made production error summaries report signal-storage failures that were not failures. It now logs `dedup_suppressed` at INFO and re-raises unchanged. Test: `tests/test_store_signal_dedup_log_20261101.py`. Operations notes for the same evening: `docs/operations/SERVER_OPERATIONS_HANDOFF_20261101.md` §7.


## Continuation, 1 November 2026 — pegged tokens excluded from scanning and training (server session)

Production evidence (Contabo host, 1 Nov): no signal issued since 2026-10-11; the discovered crypto universe was mostly stablecoins and tokenized reserves with no usable candles, and the serving ML model scored USDS/PYUSD/RLUSD/PAXG/XAUT at 0.87–0.93 against 0.05–0.64 for real coins. See `docs/operations/SERVER_OPERATIONS_HANDOFF_20261101.md`.

- New `core/pegged_assets.py` recognises stablecoins, tokenized gold and tokenized treasuries by list and by naming pattern (bases starting or ending with `USD`, starting with `EUR`). Patterns apply only to crypto-quoted pairs, so forex (`USDJPY`, `EURUSD`) and commodities (`XAUUSD`) are untouched. `PEGGED_ASSET_FILTER_ENABLED=0` disables it and `PEGGED_ASSET_EXTRA_BASES` extends it without a release.
- Applied in four places: pair discovery (`_is_non_trading_quote_asset`), the database registry universe, the engine's merged universe (managed + pinned + discovered), and ML training (`_exclude_pegged_assets`, recorded in `df.attrs["pegged_assets_excluded"]`).
- Tests: `tests/test_pegged_assets_20261101.py` (42 cases); 89 existing universe/discovery/training tests pass (Linux, Python 3.11, no PostgreSQL).
- This branch auto-deploys to production; no financial permission changed.

## Continuation, 1 November 2026 — engine cycle, external contracts, frontend, unbounded waits and production (owner request)

Commits `028fc0c3` (time limits, Bybit signature, contract tests) and `43aa34e8` (engine cycle harness). Not pushed: see the production correction below.

The owner asked for the gaps left on 30 October to be covered. Method, results and every finding: `docs/release/evidence/continuation-20261101/coverage_gaps_closed.json`.

- **Production correction.** On 1 November, read-only public requests showed production running this branch at `376fe90b`, the last pushed commit.
  - The domain is served by Caddy and uvicorn on a separate server (`157.173.99.72`). Railway shows the `SignalRankAI` service offline, with no active deployment.
  - The 30 October entries say "Nothing was deployed". That was checked on Railway only, and pushes to this branch now appear to reach production.
  - Later commits are held locally until the owner confirms how that server deploys.
- **A real engine cycle (CX-SIG-01).** `scripts/engine_cycle_harness.py` runs `engine.core.main_loop` for one batch on local PostgreSQL.
  - All outbound connections are blocked. Synthetic candles go into the PostgreSQL candle cache, which the real data layer falls back to.
  - Only network edges are replaced: the live quote, the external AI reviewer, the Redis active-trade snapshot and Telegram.
  - Result: 13 strategy signals passed through every gate into one stored EMA Trend signal (score 85.75). Every VIP test user received it with Telegram proof, in three repeated runs.
  - About 60 other synthetic price paths were rejected by the real gates (quality, stop width, ML, EMA distance, trend strength, volatility).
- **Engine findings left for the owner:**
  - A cycle with no candidates skips the end-of-cycle pause, so the engine scans back to back. Changing it would alter signal timing.
  - The ATR stop repair in `SignalController` has never run: it imports from the wrong module and passes a function where a coroutine is expected. Fixing it would start rewriting generated stops and targets.
  - Without Redis, without the AI reviewers, or without a live quote, candidates or deliveries are refused. All three fail closed by design.
- **Unbounded waits (117 reviewed).** A `run_sync` with no time limit waits forever, and a hung scheduler job never runs again.
  - 55 calls now have a limit sized below their job interval.
  - 44 data-connector calls are bounded by their HTTP timeouts, and 7 are bounded sleeps.
  - Left unbounded by design: the forever engine loop and command-line entry points.
  - Left for the owner: the jobs that place or cancel broker orders or switch execution modes.
  - A guard test enforces this list.
- **External contracts, offline (CX-BRK-04, CX-TG-01).** No real messages, orders or charges were made.
  - **Bybit; fixed.** Requests were signed over a sorted query but sent in insertion order, so order-status and closed-P&L reads would fail "error sign" on a real key. A request now sends exactly the string it signed. Contract tests recompute every signature from the request as sent.
  - **Telegram.** Every tier's message, the delivery path's messages with hostile text, and all buttons meet the Bot API's HTML, length and callback-data rules. No violations were found.
  - **Paystack.** The webhook signature and the checkout payload match the provider's documented contract.
  - Broker conformance on a real sandbox account still needs credentials (CX-BRK-04 unchanged).
- **Frontend (CX-WEB-01).**
  - All frontend unit suites, lint, type check and the production build pass.
  - Headless Chromium on the local stack visited 24 public pages and 16 workspace sections while signed in. It found no HTTP, console, page or API errors.
  - Rewrites to the backend are computed at build time. The production Dockerfile and the Railway web service both supply the origin, so production is unaffected.
- **Verified:** 8 Bybit contract tests (3 fail on the previous code), 8 Telegram contract tests and the time-limit guard test. 870 related tests pass. Full Python suite at `43aa34e8` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,385 passed, 3 failed, 2 skipped**. The failures are V7 governance freshness (regenerated next), the environmental `release_provenance[isolated_metadata]` case, and a source-text test that looked for the old unbounded `run_sync(_fetch())` line. That test was updated to the new line, and its file now passes (13 tests).

## Continuation, 30 October 2026 — whole-codebase database audit and the signal pipeline on PostgreSQL (owner request)

Commits `71224344` (fixes and tests) and `3b90fa7d` (weekly report). Nothing was deployed.

The owner asked for the whole codebase to be accounted for, including signal generation, delivery and outcome tracking, not only the listed items. Two steps:

1. Every non-test Python file (770 files, 227,508 lines) was scanned for this week's bug classes, and each candidate was read by hand.
2. The pipeline was run end to end on a migrated PostgreSQL 17 database, with only the Telegram Bot API and the market-data providers replaced.

The method, coverage and outcome of every finding are in `docs/release/evidence/continuation-20261030/codebase_db_audit.json`.

- **Engine signals reached no recipient (CX-SIG-41, CX-MU-03); fixed.** This regression exists only on this branch; `main` is unaffected. Promoting the branch before this fix would have stopped engine signal delivery.
  - Cause: the engine stores a signal, then reserves it for each user through `get_or_create_signal`. Since commits `908f6cb3` and `21eec11f` (2 October), the minimum-interval duplicate check matched that same stored row and blocked every reservation.
  - Fix: a payload that carries its stored `signal_id` now reuses that row, but only while the signal is open and its levels match the payload.
  - New candidates are still suppressed, so no duplicate rule was loosened.
- **Free-pool and extra-signal delivery (CX-MU-03); fixed.**
  - The payload was built from the stored row without its creation time, so the final freshness check blocked every send.
  - The send also ran while holding the reservation session. With one critical database slot, the sender's own sessions waited on it and timed out after 5 seconds.
  - The pool now skips signals past their time-to-telegraph limit, which final send rejects anyway. No limit was changed.
  - Refreshing engagement buttons no longer holds a session across one Telegram edit per recipient.
- **Time zones (CX-NOTIF-01, CX-CAL-03, CX-SIG-50).** 304 of the 313 timestamp columns have no time zone, and asyncpg refuses time-zone-aware values for them. Most callers swallowed that error into an empty result. Fixed:
  - `/proof` reported 0 outcomes;
  - `/strategies` (two copies) and owner `/users`;
  - the weekly filter report;
  - the cached calendar fallback, which also returned a field name the news gate does not read;
  - execution bookkeeping, the drawdown circuit breaker and broker reconciliation.

  Left unchanged for an owner decision: the smart-exit job still fails, because fixing it would let it send automatic broker close orders.
- **Rows read after a rollback; fixed.** `/verifybroker` failed for every existing user. Also fixed: legacy Bybit credentials, the legacy `/paystack/charge` and waitlist logging.
- **A session held while another was opened.** By default one session at a time gets the critical database slot, so a second session opened inside the first waits 5 seconds and fails.
  - Fixed: the weekly owner report ran inside the session that checked its schedule, so its own query failed and it reported 0 delivered outcomes.
  - Left for the owner: switching to live MetaTrader mode (`PUT /execution-settings`) looks up the account in a second session. On default settings that lookup fails, so the switch is likely refused. Fixing it would let users turn on live broker mode.
  - The Bybit execution router has the same pattern and was not changed.
- **Recorded, not changed:**
  - Three paths still hold a session during Telegram sends: the startup message refresh (off by default), the owner correction notifier and the legacy engine notifier (off by default).
  - The unused legacy ML collector also leaves out `tp3` wins. The live trainer includes them.
  - The news worker writes a Redis key that nothing reads.
  - 117 `run_sync` calls have no timeout. They are listed but were not reviewed one by one.
  - 203 broad exception handlers return a fixed boolean. The 19 in gate functions were reviewed: each matches an owner decision or fails closed.
- **Verified:**
  - 7 pipeline tests and 6 read-regression tests on PostgreSQL. The 12 that reproduce a bug each fail on the previous code; the missed-entry expiry case found none. The pipeline tests cover:
    - delivery once;
    - entry → TP1 → TP2 → TP3 at 3R, with the recipient notified once and `/proof` counting it;
    - a losing short to two recipients;
    - a free-pool send;
    - the background tracker scan;
    - an untouched entry expiring as missed, with no R.
  - Two static guards over every non-test Python file, which list every fixed site when run on the old code, plus a live-schema check of which tables store time zones.
  - 675 related tests pass. Full Python suite at `71224344` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,367 passed, 2 failed, 2 skipped**. The failures are V7 governance freshness (regenerated next) and the environmental `release_provenance[isolated_metadata]` case. `3b90fa7d` was verified with 18 targeted PostgreSQL tests and 164 related tests.

  Signal generation from live market data was not run: the pipeline tests start from a stored, quality-gated signal.

## Continuation, 30 October 2026 — prop dashboard, and a broker-account read crash (owner request)

Commits `9734fd2b` (read fix), `7eb0d9f5` (dashboard data), `01fbd61a` (web view) and `f89697eb` (governance). Nothing was deployed.

- **Bug found and fixed (CX-SEC-04, CX-PROP-03).** Five broker-account functions read database rows after a rollback, which expires them: `get_account_policy`, `reconciliation_snapshot`, `list_account_ledger`, `evaluate_persisted_account_policy` and `record_reconciliation`. On real PostgreSQL every call raised `DetachedInstanceError` whenever the row existed. So:
  - the policy and ledger endpoints errored for any account with a policy or ledger entries;
  - the execution admission check crashed, failing closed.

  The existing tests used in-memory fakes and could not see it. All five now copy what they need first, and a PostgreSQL test drives them against real rows.
- **Prop dashboard (CX-PROP-04).** The Brokers view shows, for any account with a policy:
  - today's loss and total drawdown as meters of the effective limit, using the execution gate's own formulas, limits and the account's reset time zone;
  - current, day-start and highest equity.

  For PROP accounts it adds trading days (days with fills) against the minimum, profit-target progress, and a form for starting balance, target and minimum trading days. Those objectives come from the firm's rules as the owner enters them, are stored on the connection and are display-only: no gate reads them, and saving them leaves the risk policy, its version and certification unchanged. Missing or stale (over 15 minutes) broker data shows as unavailable, never as zero. No firm rules were invented; CX-PROP-02 (verified rule profiles) remains an owner decision.
- **Verified:**
  - 12 dashboard tests (2 on PostgreSQL), including agreement with `evaluate_account_policy` on the same numbers;
  - 1 PostgreSQL regression test for the read fix;
  - a headless-Chromium run on the owned local stack with a synthetic PROP account: every figure matched a hand calculation, saving objectives left the policy at version 1, and axe WCAG 2.2 AA found no violations in either theme. Full suite at `f89697eb` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,354 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.

## Continuation, 30 October 2026 — economic calendar and news blackout (owner request)

Commits `d6949b09` (fix and tests) and `c27ced4d` (governance). Nothing was deployed.

Writing tests for the economic calendar (CX-RISK-01, CX-SIG-22) exposed five bugs, all fixed:

- **The blackout never blocked anything in the all-in-one runtime.** `railway_main` runs the engine loop in an executor thread. There the sync gate's `asyncio.get_event_loop()` raised, and the wrapper swallowed the error and returned False. The gate now uses `utils.async_runner.run_sync` with a 20-second bound. When it cannot be evaluated it still does not block (existing policy), but logs a warning at most every 10 minutes.
- **One failed feed fetch disabled news protection everywhere for an hour.** The timeless static fallback was cached in Redis. It is no longer shared, old entries are ignored, and the live feeds are retried after 5 minutes. `calendar_status()` reports whether real event times are loaded.
- **The database copy of the calendar was always empty.** The sync worker read `event_date` while events carry `event_time`. It also compared timezone-aware values with the naive column, which PostgreSQL rejects (reproduced locally). It now stores naive UTC.
- **The database and Redis copies dropped just-past events,** losing the blackout after a release; they keep the last 2 hours.
- **`EUR/USD`-style symbols were not recognised.**
- **Tests:** 10 new (1 on real PostgreSQL); 6 of them fail on the previous code; 261 related tests pass. Full suite at `c27ced4d` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,337 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.
- **Behaviour change after promotion:** the 60-minute blackout around high-impact USD events will actually suppress signals for USD-sensitive assets (major USD pairs, gold and silver, BTC/ETH and the US indices) in the all-in-one runtime. This was always the design, but it was not working there.
- **Owner decision (30 Oct): keep fail-open.** When no calendar source is available the gate lets trading continue; fail-closed would stop USD-sensitive signals during every feed outage. Recorded in `requirements_conflicts.md` and locked by `tests/test_owner_decisions_20261030.py`, which also checks the blackout still blocks when event times exist.

## Continuation, 29 October 2026 — backtest execution realism (owner request)

Commits `a062edd9` (harness) and `516b2023` (governance). Research tooling only; nothing deployed and no engine behaviour changed.

- **Problem (CX-BT-01).** `scripts/backtest_zone_rejection.py` had four optimistic assumptions:
  - it filled every trade at the signal bar's close, a price known only once that bar has closed;
  - it filled targets on a touch;
  - it ignored gaps through stops;
  - it charged one flat round-trip percentage.
- **New default execution (`--cost-model realistic`).** It follows the conventions of `engine/backtest_execution.py`:
  - **Entry:** a market order at the next bar's open, paying half the spread plus slippage. An open already past the stop or target cancels the trade (`no_fill`).
  - **Stops:** fill at the stop, or at the open on a gap, so losses can exceed 1R.
  - **Targets:** limit orders that fill only when price trades through by half the spread, with no price improvement.
  - **Fees and funding:** taker fees on market and stop fills, maker fees on targets, optional perpetual funding.
  - **Reporting:** R stays the planned risk. Each trade reports its fills, `fees_r` and `friction_r`.

  Defaults (5/2/2/3 bps) suit liquid crypto majors and are all flags. `--cost-model flat` reproduces the 28 Oct model for comparison.
- **Verified:** 8 new tests with hand-computed fills, fees and funding; the command-line path was checked end to end on a 200-day synthetic random walk, where friction was 0.07–0.20R per trade. That is plumbing evidence, not strategy evidence: market-data hosts are still unreachable from this machine, so no real-data backtest has been run. Full suite at `516b2023` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,327 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.
- **Still not modelled:** order-book depth and market impact, partial fills, borrow costs and corporate actions.

## Continuation, 29 October 2026 — owner Telegram menu (owner request)

Commits `767e6e95` (fix) and `2f892415` (governance). Nothing was deployed.

- **Problem (CX-TG-01).** The owner can use 123 catalogue commands, and Telegram's menu holds 100 per scope. The list was cut in catalogue order, so the owner's menu lost the 23 commands at the end. These were the owner's own controls: `kill_switch`, `system_health`, `queue_status`, `queue_replay`, `release_status`, and the audit and dead-letter tools.
- **Fix.** For owner and admin menus over the limit, 25 customer onboarding, buying, referral and setup commands are left out of the menu (`OPERATOR_MENU_OMIT` in `signalrank_telegram/command_catalog.py`). If the catalogue outgrows that too, operator commands are kept before customer ones. The owner menu now has 98 commands, including all 55 operator commands. Customer menus and the admin menu (98) are unchanged. Every command still works when typed, and `/help` still lists all of them. The bot republishes menus when it starts.
- **Tests:** 6 new; 276 related tests pass. Full suite at `2f892415` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,319 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.
- **Local environment note:** the owned PostgreSQL test cluster stopped at 19:23 after a Windows process-start failure (`0xC0000142`). It was restarted, recovered cleanly, and the throwaway full-suite databases from earlier runs were dropped.

## Continuation, 29 October 2026 — client address trust (owner request)

Commits `57e56058` (fix) and `bf067ce2` (governance). Nothing was deployed; production still runs `9865a3d1`.

- **Problem.** Rate limits, the IP stored with security events, and the Paystack webhook IP allowlist all took the first `X-Forwarded-For` value, which the client chooses. Railway's public networking specification says its edge sets `X-Real-IP` to the client's remote address, and does not mention setting `X-Forwarded-For`. The production domain resolves directly to Railway's edge, with no CDN in front.
- **Fix (CX-SEC-02, threat TM-42).** `core/client_ip.py` trusts, in order:
  1. an address signed by our web proxy (HMAC-SHA256 with `SIGNALRANK_CLIENT_IP_SECRET`, 5-minute window);
  2. `X-Real-IP` on Railway (override with `TRUSTED_CLIENT_IP_HEADER`);
  3. the socket peer.

  The first `X-Forwarded-For` value is never used. The rate limiter, security events and the Paystack allowlist all use this resolver. The Next.js proxy no longer forwards browser-supplied forwarding headers: it passes the edge-set address, signed when the secret is set.
- **Owner check after deployment.** New owner-only `GET /api/v1/platform/operator/request-identity` shows the address and source the server derived from your own request.
- **Not observed.** That the edge replaces a client-supplied `X-Real-IP` comes from Railway's documentation; production cannot be inspected without deploying. Reading the web service's variables (to learn whether the web app reaches the API privately or through the public edge) was refused by the production-read guard and not attempted another way.
- **Tests:** 14 Python and 4 frontend tests, including a signature test vector shared by both languages; 475 related Python tests pass. Full suite at `bf067ce2` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,313 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.

## Continuation, 29 October 2026 — threat model revision, security fixes, accessibility audit (owner request)

Commits `6360f648`, `0243af1f`, `8c2c15e4` and `64e5653d` (security fixes); `6bc1f02b` (threat model); `d9d28e15` (accessibility); `28c0c39e` (governance). Nothing was deployed; production still runs `9865a3d1`.

- **Threat model (CX-SEC-01).** `docs/security/THREAT_MODEL.md` gains section 12, extending the 26 Sep model (schema `0045`) to `0057`. It covers new surfaces, trust boundaries TB-09 to TB-13 and threats TM-28 to TM-41, each with the control read in the code and its tests. Sections 1–11 are unchanged. Open items are stated as risks, not exploit steps, because the repository is public.
- **Fixed while modelling (CX-SEC-02):**
  - **Webhook address pinning:** a delivery now connects only to the address that passed validation, which closes DNS rebinding. Non-public ranges are refused, TLS is still verified against the real hostname, and connections are not reused across customers.
  - **Per-account sign-in limit:** 10 failed passwords in 15 minutes lock password sign-in, whatever the forwarded IP. Unknown emails are counted too, so the lock reveals nothing.
  - **Account email cap:** at most 5 sign-in-link and 5 reset emails per account per hour, with an identical reply when capped.
  - **Private-chat-only bot commands:** in groups, only eight public-information commands answer.
- **Supply chain and secrets (CX-SEC-06, CX-AUTH-04).** On 29 Oct, `pip-audit` on `requirements.lock` found 0 known vulnerabilities in 135 packages, and `npm audit --omit=dev` found 0. A secret-pattern scan of tracked files found only false positives.
- **Accessibility (CX-WEB-02).** New `scripts/a11y_audit.py` runs axe-core's WCAG 2.2 A/AA rules on 40 pages (public, legal, workspace), in two themes at two widths. A 320 px pass adds reflow, skip-link and visible-focus checks. Before the fixes, 128 of 140 runs failed (1,067 colour-contrast nodes, 62 name mismatches); after, 0 of 200 fail. The fixes:
  - muted-text tokens now meet at least 4.8:1 and 5.3:1;
  - the menu's accessible name starts with "Menu";
  - public pages have a skip link;
  - the legal pages' mis-encoded link name is corrected.

  Evidence: `docs/release/evidence/continuation-20261029/a11y_audit.json`. Screen readers, full keyboard journeys and real devices remain manual.
- **Tests:** 17 new Python tests (5 on real PostgreSQL) and 3 new frontend tests; 598 related Python tests pass. Full suite at `28c0c39e` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,299 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.
- **Still open:** confirm how the hosting edge sets `X-Forwarded-For` before changing IP-keyed rate limits; an external security review (CX-SEC-07); manual accessibility checks.

## Continuation, 29 October 2026 — Telegram /watchlist and /journal (owner request)

Commits `5b2ef71a` (commands and shared services), `e09f65ce` (governance), `17c15b15` (web watchlist controls), `f591ceca` (governance). Nothing was deployed; production still runs `9865a3d1`.

- **Shared services (CX-CHAN-01, CX-PROD-03).** `services/platform/watchlists.py` and `services/platform/journal.py` now hold the SQL the web endpoints used; the web endpoints and the bot both call them, so a list or entry made in one channel appears in the other for the same canonical account. Web responses are unchanged apart from two additions: a blank watchlist name is refused (422), and each watchlist item carries its `display_symbol`.
- **`/watchlist`** (free, as on the web): list every watchlist with symbols; `add`/`remove` by symbol or exact instrument id; `new`; `delete <name> confirm`. A symbol shared by several active instruments (for example spot and perpetual) is never guessed: the candidates are listed. A mistyped symbol creates nothing; only a successful add creates the default list.
- **`/journal`** (free): the latest five entries; `add <text> #tags`; `delete <id> confirm` with a short id (six or more characters, own entries only).
- Both commands answer only in a private chat, so journal content is never posted to a group.
- **Web watchlists** now show symbols, remove one instrument at a time, and delete a list after a second click. Before this, the web had neither control even though the API offered both. A presentation test that pinned "no DELETE calls" now allows exactly those two routes.
- **Parity matrix:** the watchlists and journal sections now map to commands. The generator now lets a singular command match its plural route, which adds 10 route matches; each was reviewed and is a true match.
- **Verified** end to end on the owned local stack: a list and an entry made through the real bot handlers appeared on the web pages, and an entry, a removal and a deletion made on the web were reflected by the bot. Real Telegram delivery was not exercised: no bot token was used locally.
- **Known limit (pre-existing):** Telegram's command menu holds at most 100 commands per scope. Every tier's menu includes both new commands (free 40 of 40, admin 98 of 98), but the owner menu shows 100 of 123 catalogue entries (previously 100 of 121), so the last 23 owner and admin entries are missing from it. `/help` still lists all of them. *(Fixed later on 29 Oct: the owner menu now keeps every operator command.)*
- **Tests:** 9 new Python tests (7 on real PostgreSQL) and 3 new frontend tests; 358 related Python tests pass. Full suite at `e09f65ce`: 4,282 passed, 1 failed, 2 skipped. Full suite at the final code commit `f591ceca` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,282 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case.

## Continuation, 29 October 2026 — engine reliability: bounded database calls, owner alerts, owner screens

Commits `b0bf1c78` (timeouts), `3bfda44a` (owner alerts), `510dd352` (owner screens), `86cd8c6d` (docstring correction), `82c35b66` (governance). Nothing was deployed; production still runs `9865a3d1`. No financial permission changed.

- **Bounded database calls (CX-Q-05).** The five `run_sync` database calls in the engine loop that had no timeout (decision log, ML rejection record, ML prediction log, exposure check, notification fan-out) now carry `ENGINE_DB_CALL_TIMEOUT_SECONDS` (default 10 s, clamped to 1–120 s; the fan-out has a 45 s outer bound). The exposure check refuses the trade on a timeout. `run_sync` ignored its timeout when background threads were disabled; fixed. A source test fails if an unbounded call is added. *Correction:* the 28 Oct sections said thirteen calls were unbounded; the count was five, plus one fallback reached only when the async runner cannot be imported.
- **Owner alerts (CX-OBS-04).** Telegram alerts to `OWNER_IDS`, de-duplicated across processes, each ending with a runbook line: `engine_stalled` (sent by the stall watchdog before a dedicated engine exits); `engine_silent` (a worker loop, `OWNER_ALERTS_ENABLED` default on, every `OWNER_ALERTS_INTERVAL_SECONDS`=120, when the engine heartbeat is missing, stalled or older than `OWNER_ALERT_ENGINE_SILENT_SECONDS`=900); `queue_age` (oldest undelivered `event_outbox` row or Telegram update older than `OWNER_ALERT_QUEUE_AGE_SECONDS`=300); the existing `provider_outage` alert now carries its runbook. The queue-age reads are read-only and never create a stream or group. Delivery to real Telegram was not exercised.
- **Owner web screens (CX-RISK-04, CX-USER-02, CX-COST-01, CX-ADMIN-01).** Operations gains scoped kill switches (engage with a reason and the typed phrase `ENGAGE`, two-step release, audit trail), account-merge review (read-only preview; owner-only apply needing a tick and the exact merge id) and AI spend (budgets, spend by provider, workload, model and user). The backend still enforces owner authority, confirmation and a recent sign-in. Exercised end to end on the owned local stack with a synthetic owner: a switch engaged and released, a merge refused for a wrong id and completed for the right one (two watchlists, a journal entry and the Telegram identity moved), spend shown from three ledger calls; no horizontal overflow at 375 px.
- **Tests.** 5 timeout tests, 10 alert tests (1 on real PostgreSQL), 4 frontend contract tests; 338 related Python tests pass; frontend 71 transport and 38 presentation tests, `tsc` and `eslint` clean. Full Python suite at `82c35b66` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,273 passed, 1 failed, 2 skipped**; the failure is the environmental `release_provenance[isolated_metadata]` case seen in earlier runs.
- **Still blocked on the owner:** `PROMOTE_TO_PRODUCTION` (migrations `0054`–`0057`), provider keys and plans, a staging environment, GitHub Actions billing.

## Continuation, 28 October 2026 — shadow evidence for the expectancy gate (owner decision)

Commits `136290b8` (feature), `4ad62330` (schema head `0057_expectancy_shadow_index`), `698a0191` (promotion plan). The owner chose to build shadow evidence and keep `EXPECTANCY_HARD_BLOCK_ENABLED` on. Nothing was deployed.

- Candidates refused only for `expectancy_unavailable` are recorded once per setup as `decision_log` rows with `layer='expectancy'` (de-duplicated 24 h; `EXPECTANCY_SHADOW_RECORDING_ENABLED`, default on).
- A second shadow tracker (`layer='expectancy'`, own cursor and health key) follows them to stop or final target and stores realized R; ambiguous bars count as −1 R; it writes no ML shadow predictions or metrics.
- With `EXPECTANCY_SHADOW_BOOTSTRAP_ENABLED=1` (default off) the gate may use that evidence only with at least twice the live minimum sample (20) and only if the lower 95% bound of expectancy after a 0.05 R cost haircut is at least `EXPECTANCY_MIN` (0.15 R); the gate sees that bound, never the mean.
- Migration `0057_expectancy_shadow_index`: concurrent, validated partial index; `EXPLAIN` on a 50,000-row table shows index scans for both the tracker and the evidence query; upgrade/downgrade/upgrade passed.
- Tests: 8 new (2 on real PostgreSQL); 207 related tests pass. Full Python suite at `698a0191` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0057`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,258 passed, 2 failed, 2 skipped**; failures are V7 governance freshness (regenerated next) and the environmental `release_provenance[isolated_metadata]` case.
- Expected timeline after promotion: shadow trades accumulate while the engine runs; with the flag on, the first asset can qualify only after 20 tracked outcomes with a strongly positive lower bound. Until then the gate stays shut, by design.

## Continuation, 28 October 2026 — third pass: signal blockers, AI cost ledger, parity, data providers

Branch `feat/frontend-rebuild-and-stage1-hardening`, commits `8495d912` … `42f212a2` after `f3dd85c7`. Stage 1 and release remain NO-GO. Railway was read only except the owner-approved engine restart recorded above; nothing was deployed or migrated in production.

- **Crypto signals are blocked by an expectancy lockout (finding, not changed).** Production sets `EXPECTANCY_HARD_BLOCK_ENABLED`; `live_expectancy` is only populated from at least `EXPECTANCY_MIN_SAMPLE` (10) proof-backed delivered outcomes in 30 days. With no deliveries since early October, every candidate is refused with `risk/expectancy_unavailable` and the gate can never reopen by itself. Shadow tracking covers only ML-layer rejections, so no counterfactual evidence accumulates either. Resolving it is an owner decision (see the blockers list); no gate or threshold was changed.
- **Data providers (`8495d912`).** Connectors returned `[]` for every failure and logged the cause only at debug level, so production showed `insufficient_candles candles=0` for all FX/index/commodity requests. They now record the cause (`api_key_missing`, `rate_limit_cooldown_active`, `http_NNN`, `empty_response`, ...), which the fetcher appends to the failure reason, warned once per window. Defects fixed: Polygon received raw platform symbols instead of `I:`/`C:`/`X:` tickers; yfinance asked Yahoo for `BRENT` (now `BZ=F`), had no index mapping, and builds 4h bars from UTC-aligned 1h bars. 29 tests.
- **AI cost and usage ledger (CX-COST-01, CX-AI-06; `ab68f97b`).** Migration `0056_ai_usage_ledger` (append-only tables by trigger); every OpenAI/Gemini call reserves worst-case cost before the call and settles after; budgets from the environment are enforced under an advisory lock and an exhausted budget skips the AI step (deterministic review applies); without budgets it records only. `/operator/ai-spend` summarises spend. 16 tests on real PostgreSQL; `0053 → 0056 → 0053 → 0056` rehearsed on seeded data with `auto_renew` values unchanged. Every `EXPECTED_ALEMBIC_HEAD` pin moved to `0056_ai_usage_ledger` (`234c6231`).
- **Web/Telegram parity (CX-CHAN-01, CX-TG-01; `a3cd967d`).** Quality, privacy, feedback and operator authority are shared services used by the web API and the bot; `/quality`, `/privacy`, `/feedback` and `/account_merges` added or extended in Telegram; mutating owner controls stay web-only. `TELEGRAM_WEB_PARITY_MATRIX.md` is generated from the code (`scripts/build_parity_matrix.py`); remaining gaps it names include watchlists and the journal. 33 tests.
- **Order-block ABC strategy (`267a3339`, `42f212a2`).** Closed-bar-only evaluation, stop beyond every extreme since C, day-correct 4h dealing range and daily-to-4h mapping fixed (16 tests). A causal replay backtest harness was added (5 tests) but not run on real data: Binance, Coinbase, Bybit, KuCoin, OKX, Kraken, Gate.io and Dukascopy were unreachable from this machine (DNS/network filtering). The strategy stays disabled.
- **Work from the three sessions that stopped at their usage limit** (AI ledger, backtest, parity) was found uncommitted in this worktree, reviewed, completed where needed (one raw-exception Telegram reply fixed, missing parity matrix written, head pins and one source-pinned test updated) and committed separately.
- Full Python suite at `42f212a2` (Windows 11, Python 3.13.7, owned PostgreSQL 17 migrated from empty to `0056`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,250 passed, 2 failed, 2 skipped**. Failures: V7 governance freshness (artifacts regenerated in the following commit) and the environmental `release_provenance[isolated_metadata]` case (`alembic` only in user site-packages, excluded by `python -I`).

## Continuation, 28 October 2026 — engine stall root cause, owner strategy, dependency verification

Branch `feat/frontend-rebuild-and-stage1-hardening`, commits `6c14af7d` and `5b7eb4c5` after `dce7bd8c`. Stage 1 and release remain NO-GO. Railway was read only (environment status, deployment lists and logs); nothing was deployed, restarted, migrated or reconfigured.

- **Production engine root cause (CX-Q-05, CX-FACT-06).** `striking-optimism` logged its last pipeline step at 2026-10-22 08:08:30 UTC (`PENGUUSDT`), immediately after `Postgres-R8Lr` was redeployed at 08:07:47 and the engine's connections broke at 08:08:35; it has logged nothing since, yet Railway reports it Online with one running replica and no failures. Thirteen database calls in the loop use `run_sync` without a timeout. *(Corrected 29 Oct: five calls, not thirteen; all bounded since `b0bf1c78`.)* Fix: an engine stall watchdog that logs the stuck call's stack, publishes a not-ready `stalled` heartbeat and, for a dedicated engine role, exits with code 70 so the `ON_FAILURE` policy restarts it (`5b7eb4c5`, 7 tests). Not deployed: the running engine stays stalled until it is restarted.
- **Engine restarted at the owner's request** (28 Oct, ~05:40 UTC; `striking-optimism` restarted in place on deployment `d6423329`, still `9865a3d1`; no deploy, migration or configuration change). Production `/readyz` became `ready` with every check passing for the first time since the stall; cycles 5→11 in about five minutes with heartbeat age under 60 s. Signals remain 0: crypto candidates (18–38 per batch, scores up to 81) are refused by the risk gate with `risk/expectancy_unavailable`, and FX/index/commodity assets have no candles from their providers. Gates unchanged; these need an owner decision (expectancy bootstrap) and provider fixes.
- **Other signal-drought causes seen in the same logs (not changed):** several FX, index and commodity providers returned 0 candles (Tiingo, Twelve Data, Polygon, yfinance), and BTCUSDT candidates were refused with `risk/expectancy_unavailable`.
- **PR #202 was not deployed.** Railway created no deployment for `4f4f6d33`; every application service still runs `9865a3d1` (12 Oct). Earlier pushes show automatic deployments SKIPPED and later deployed manually.
- **Owner strategy videos.** The 23 Jun 2026 (XAUUSD) and 6 Aug 2026 (USDCAD) recordings were reviewed from 67 extracted frames and a machine transcript (the first recording's audio is unusable). Implemented as `strategies/zone_rejection.py` (`Order Block ABC (Top-Down)`, `order-block-abc-v1`): 1d/4h order block, premium/discount filter on the 1d range, 4h break of structure, 15m (else 5m) ABC where C takes A and the latest closed bar is the first close through B, target the nearer of the 50% equilibrium and the 4h liquidity, minimum 2R. Group `zones`, 5m/15m capability, disabled unless `ZONE_REJECTION_STRATEGY_ENABLED` is set (`6c14af7d`, 11 tests). No backtest or shadow evidence yet; enabling needs owner approval.
- **Full Python suite with the upgraded dependencies** at `fa223df4` (Python 3.12 venv from `requirements.lock`, owned PostgreSQL 17 migrated from empty, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,145 passed, 1 failed, 2 skipped**. The failure, `test_provider_certification_boundaries.py::test_positive_infinity_cannot_hang_any_timestamp_normalizer`, is a 15 s subprocess deadline hit by cold imports in the new venv; it passes on re-run in about 4 s (twice).

## Continuation, 27–28 October 2026 — second pass: engine diagnostics, risk, identity merge, security

Branch `feat/frontend-rebuild-and-stage1-hardening`, commits `21e5c509` … `f95f9785`. Stage 1 and release remain NO-GO; nothing was merged, deployed or migrated against any shared system, and no financial permission changed. Environment for all evidence below: Windows 11, Python 3.13.7, an owned PostgreSQL 17 cluster on `127.0.0.1:55434` created for this session, Node 22.19 with npm 11.17.0. Not CI, staging or production.

- **Engine stall diagnostics (P0).** Five early cycle exits (circuit breaker active or failing closed, no assets, off-market throttle, empty queue) wrote no `engine:last_cycle`, so a live engine skipping every cycle looked stopped. They now publish `status: skipped` with the reason; readiness still treats `skipped` as not ready and names the reason (`2288ce6e`). The production root cause still needs Railway logs.
- **Runtime identity (CX-OBS-03).** `/version` reports the code's Alembic head and a UTC build stamp written by the Nixpacks build phase (`bd257421`, `131224e7`). `image_digest` stays `unknown` under Nixpacks.
- **Migration rehearsal.** `0053 → 0055 → 0053 → 0055` with plain Alembic and `0053 → 0055` through `scripts/controlled_migrate.py`, on 5,000 users and 200,000 decision rows: existing `auto_renew` values unchanged, index valid, downgrade clean. Found that the guarded migration also needs `PRODUCTION_DB_VOLUME_SIZE_MB` and a volume observation under one hour old; the promotion plan now lists it. Evidence: `evidence/continuation-20261027/migration_rehearsal_0053_0055.json`.
- **Risk.** Audited strategy/instrument/asset-class kill switches enforced at the MT5 and Bybit chokepoints, fail closed (`31770c17`). Real-PostgreSQL race: 12 simultaneous reservations against a limit of 3 approve exactly 3; found and fixed every quota refusal being reported as `execution_quota_unavailable` (`41e16c3b`). `engine/correlation_guard.py` and `core/risk_authority.py` are not wired into runtime.
- **Focused universe in ML training** (`fdcfefe0`) and **per-strategy/instrument/timeframe/layer rejection breakdowns** on `/quality` and the web Quality view (`6cc5f94c`, `b51d3db7`).
- **Telegram ↔ web account merge.** A web account linking a Telegram identity with existing bot history stopped at `merge_review` forever. Reviewed merges can now be previewed and completed (owner endpoints, `python -m tools.complete_account_merge`) in one transaction: rows referencing the archived account move only when no unique index collides and owned parent rows move with them; nothing is deleted; credentials and sessions never move; paid tier and the renewing subscription follow the person (`3febf802`). 5 real-PostgreSQL tests.
- **Security.** Next.js `16.3.8 → 16.4.2` (critical unauthenticated RCE advisories GHSA-2464-fhr4-w9xw, GHSA-673q-mjm6-r5xr) and zod; `npm audit`: 0 vulnerabilities (`630163db`). pip-audit of `requirements.lock`: 49 advisories in aiohttp, certifi, opentelemetry-api and Pillow; bumped to aiohttp 3.14.5, certifi 2026.10.19, OpenTelemetry 1.45.1/0.66b1, Pillow 13.0.0, respecting the 7-day release-age rule (`242eefc3`). Baseline `nosniff`, `no-store` and HTTPS-only HSTS on direct API responses; HSTS on the web app (`eaa11d9d`).
- **Audit.** Global and scoped kill-switch changes now write `security_events` rows, best effort so a switch never fails on audit (`f95f9785`).
- **Web.** Production build run locally against the local API. At 320 px the public Menu button was off-screen (fixed, regression test). A window with zero quality decisions now says the engine most likely did not run. Basic accessibility sweep clean on Settings, Signals and Login.
- **Tests.** Full Python suite at `eaa11d9d` on real PostgreSQL 17 (database migrated from empty to `0055`, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`): **4,138 passed, 4 failed, 0 skipped**. Failures: V7 governance freshness (artifacts not yet regenerated at that commit; regenerated before push), `release_provenance[isolated_metadata]` (environmental: `alembic` only in user site-packages, excluded by `python -I`), and two host-timezone privacy cases that call POSIX-only `time.tzset` (now skipped where unavailable, `4d8d596d`). Frontend at `630163db`: tsc, eslint, `next build` and 108 node tests pass.
- **Production promotion** was requested again; not executed. It still needs the owner phrase `PROMOTE_TO_PRODUCTION`, Railway access for backup and `EXPECTED_RELEASE_COMMIT` on every service, and the guarded migration (plan updated with the volume gate). The promoted code would now also change the Nixpacks build phase and Python/Node dependency versions listed above.

## Continuation, 27 October 2026 — runtime schema identity

Branch `feat/frontend-rebuild-and-stage1-hardening` (from `5f848d96`; code commit `bd257421`). Stage 1 and release remain NO-GO; nothing was merged, deployed or migrated, and no financial permission changed.

- CX-OBS-03 (partial fix): `/version` now reports the code's single Alembic head when `EXPECTED_SCHEMA_HEAD` is unset, resolved independently of the working directory, instead of `unknown`. An explicit `EXPECTED_SCHEMA_HEAD` still wins. `build_timestamp` and `image_digest` still depend on build-provided variables and stay `unknown` until the build sets them. Test: `tests/test_version_schema_head_20261027.py` (3 passed locally; the first case fails on the previous code). Not deployed, so production still reports `unknown` until an authorized promotion.
- Full Python suite `pytest -q tests` at `920ca054` (local Windows 11, Python 3.13.7, no PostgreSQL, so integration tests skip): **3,950 passed, 1 failed, 161 skipped**. The failure, `test_release_provenance.py::test_migration_inspection_and_release_cli_do_not_require_pythonpath[isolated_metadata]`, is environmental: `alembic` is installed only in the user site-packages, which `python -I` excludes. Not CI, staging or production evidence.
- Production promotion was requested in chat on 27 Oct without the `PROMOTE_TO_PRODUCTION` phrase or the prerequisites in [PRODUCTION_PROMOTION_PLAN_20261024.md](PRODUCTION_PROMOTION_PLAN_20261024.md) (backup evidence, `EXPECTED_RELEASE_COMMIT` on every service, guarded `0054`/`0055` migration). Not executed.

## Continuation, 24 October 2026 — frontend rebuild, live readiness finding, independent audit

Branch `feat/frontend-rebuild-and-stage1-hardening` (from `393f3d88`; commits `7946fa25`, `840abd90`, `801780d4`, `7a63d5ac`, `8a7d3e3b` and this documentation commit). Stage 1 and release remain NO-GO; nothing was merged, deployed or migrated, and no financial permission changed.

- Web frontend rebuilt on a new design system; billing (server-priced Paystack checkout, verified confirmation, auto-renew cancel, refund review) and signal feedback wired to existing APIs. Local evidence: tsc, eslint, `next build`, 98 node tests at the time of commit; 61/61 pre-rebuild API calls and 11/11 routes retained (`frontend/scripts/api-baseline.test.mjs`).
- Focused-universe admission now guards both signal persistence paths and the MT5/Bybit execution chokepoints (no-op unless enabled in staging). HTTP 451 classified as `REGION_RESTRICTED`; Binance region blocks logged and backed off.
- Live read-only `/readyz` (deployed `9865a3d1`) returns 503: only `engine_runtime` fails — the `engine:last_cycle` heartbeat is absent, so the production engine is not cycling (Engine Pulse: 0 signals in window). Probe now reports `engine_heartbeat_missing`. Root cause needs Railway logs (blocked: access). Production DB is at `0053`; repository head `0055`.
- New owner source `message.txt` (SHA-256 `b78374d0…`) consolidated privately into 287 requirement IDs; hashes and anchors only in `evidence/continuation-20261024/source_intake.json`.
- Full Python suite at clean commit `e9b2b368` on a local PostgreSQL 16.2 database migrated from empty to `0055`: **4,098 passed, 0 failed, 1 skipped** (pyarrow not installed); multi-user isolation suite 5/5. Three pre-existing test portability/isolation defects fixed. Local only; GitHub Actions remains billing-locked. Limits in the audit §8.
- Web screens for API keys, webhooks, plan entitlements and referrals; self-service data export and audited account-deletion request (nothing deleted automatically). Fixed a host-timezone bug in the recent-sign-in check for sensitive actions. Every consolidated requirement ID assessed with evidence paths in `evidence/continuation-20261024/cx_assessment.json` (audit §9): 8 verified locally, 248 partially verified, 20 blocked, 7 awaiting approval, 5 not implemented.
- Full Python suite at `a53ac6be`: 4,108 passed, 1 failed (V7 freshness, caused by a concurrent doc edit; passes after regeneration). Production promotion plan prepared, not executed: [PRODUCTION_PROMOTION_PLAN_20261024.md](PRODUCTION_PROMOTION_PLAN_20261024.md).

Full details, classifications and information gaps: [INDEPENDENT_ACCEPTANCE_AUDIT_20261024.md](INDEPENDENT_ACCEPTANCE_AUDIT_20261024.md).

## Stage 0 safe local Git and historical forensics, 22–23 October 2026

The exact observed source is e01e7c41f49a3e35335b00edc2de97367aa2dade. Evidence: [Stage 0 forensics index](evidence/continuation-20261022/index.json).

| Check | Result and scope |
| --- | --- |
| Local Git checkout & branch | Clean checkout on fix/stage1-canonical-reconciliation-20261014; 1 unpushed commit ahead of origin |
| Non-destructive remote fetch | PASS: fetched all heads/tags without --prune; 0 stale refs reported |
| Full branch & commit audit | PASS: 247 refs, 4,695 reachable commits; 28 divergent refs with 118 unique commits match branch_dispositions.json (0 missing, 0 moved heads) |
| Worktree preservation | PASS: 18 worktrees found, 17 clean, 1 dirty (.pytest-tmp/release-ci-closure-20261007) preserved untouched |
| Migration head verification | PASS: 0055_user_renewal_default (single head confirmed) |
| Governance checks | PASS: all 5 check scripts (build_release_inventory, completion_matrix, validate_current_scope, crosschat_intake, build_v7_governance) pass with 0 drift |
| GitHub PR #201 & Ruleset | Verified: PR #201 draft open, ruleset 24410166 active, CI failed at 0 steps due to account billing lock (BLOCKED_EXTERNAL) |
| Runtime public route check | Observed: / (200 JSON), /login (404), /app (200 HTML), /healthz (200 JSON), /pricing (404) |
| Railway control-plane re-verification | BLOCKED_EXTERNAL: Railway CLI session expired; unauthenticated |


## Correction source: complete local suite, 18 October 2026

The exact tested source is 393f3d88d6018d01c3f04234cc9c44b23a5de8fc. Evidence: [correction index](evidence/continuation-20261018/correction-393f3d88/index.json).

| Check | Result and scope |
| --- | --- |
| Complete system | PASS: 4,080 passed, zero failed/errors/skips; 32 owned-local checks |
| Strict static scan | PASS: OpenGrep probe and 575-file scan, zero findings/errors |
| Legacy browser | PASS: production build with synthetic accounts and owned PostgreSQL; servers/database/key cleanup confirmed |
| Evidence wrapper tests | PASS: ten fixture tests cover clean identity, changed source, duplicate names, partial evidence and missing executables |

This evidence replaces only the local pending state for the wrapper/HTML correction. It does not replace the retained 2ee0a918 results for Next browser coverage, frontend/mobile tests, or audits whose source scope was unchanged. It proves no external integration or release acceptance.


## Exact frozen run and retained failures, 18 October 2026

The exact tested source is 2ee0a918d915549f7f5ce59d59f0a8a07d2202a9. Evidence: [frozen run index](evidence/continuation-20261018/frozen-2ee0a918/index.json). Stage 1 and release remain NO-GO.

| Check at 2ee0a918 | Result and limits |
| --- | --- |
| Complete system | PASS: 4,076 passed, no failures/errors/skips; all 32 steps |
| Next and legacy browser | PASS: real local API, migrated owned PostgreSQL, synthetic accounts; cleanup confirmed |
| Ruff / critical Pyright / source registers / isolated SDK | PASS after corrected tool invocation; critical Pyright zero errors/warnings; six SDK tests |
| Dependency audits | Runtime, SDK and frontend PASS; mobile FAIL, four high dependency rows in the Expo/node-forge advisory chain |
| Bandit | PASS at configured severity/confidence threshold; not zero findings across all thresholds |
| Legacy type budget | PASS budget with 1,102 errors and six warnings; not zero-error type checking |
| OpenGrep | FAIL: zero reported findings, 575 files scanned, two HTML partial-parse errors; incomplete scans cannot pass |

The initial missing Ruff path and restricted subprocess import-discovery failures are retained. The same manifest passes once the runtime is discoverable. The synthetic receipt-overwrite probe is explicitly excluded from product acceptance; four failing regression cases are preserved alongside the ten-test modified-source correction pass. The subsequent HTML/wrapper edits require a new frozen receipt. Earlier frontend/mobile unit/export evidence remains attached to 7c3f7e0f, not relabelled as 2ee0a918. Native devices, real providers/brokers, staging, payments and soak remain unverified.

## Verification continuation, 18 October 2026

Clean unchanged 7c3f7e0f completed the full local system run: 4,075 passed,
one failed, zero skipped. The sole failure is the generated V7 governance
inventory, which was produced before the final retained evidence and register
updates. The failure is retained in evidence/continuation-20261018/index.json;
no runtime behavior is waived by identifying the generator-order error.

On that same commit, all five local manifest gates, 63 frontend tests, 53 mobile
tests, frontend lint, mobile typecheck, Android/iOS JS exports and the real Next
browser drill passed. The browser drill used synthetic accounts and an owned
migrated PostgreSQL database; server/database/key cleanup succeeded. These are
local checks, not native-device, provider, broker, financial or staging approval.
Stage 1 and the overall release remain NO-GO.

Generation order for the correction: retain/stage evidence logs first, update
baseline/docs, build_release_inventory, crosschat_intake, then build_v7_governance.
Check all three without writing before freezing. Do not add evidence after the
final governance generation without regenerating it. Run the full suite and
remaining browser/security checks from that exact unchanged correction commit.

Verification follow-up: 5f7ae60c passed the five local manifest gates, 63 frontend
and 53 mobile tests, but its full run was interrupted after an Android export
rewrote tracked legacy build artifacts. Those generated files were restored;
future exports target ignored artifacts. Missing Chromium is being installed.
A synthetic probe also exposed missing receipt metadata validation in the new
intake validator; environment, command, timestamp and scope are now mandatory,
with four negative regressions. No requirement was promoted to VERIFIED.
The next frozen commit must supply fresh full-suite acceptance.

## New source intake and diagnostic evidence, 17 October 2026

The two original document bodies were reconstructed in order and compared with
all 14,226 supplied ledger texts, their SHA-256 hashes, and the complete text
exports. The ordered 1,586 headings and 242 seeds also validate. Source files
remain private; crosschat_source_index.json contains their hashes and anchors.
No semantic completion is inferred. requirements_universe.jsonl links the new
corpus and prior source/interface inventory without replacing prior IDs.

Retained diagnostics are in evidence/continuation-20261017/index.json:
- crosschat-intake-diagnostic-20261017: exit 1, 70 passed / one local DB setup
  error; the owned test server was stopped.
- crosschat-intake-diagnostic-r2-20261017: exit 0, 71 passed / no skips, same
  dirty but unchanged source after restarting only the test cluster.
- frozen-local-manifest-a23e088f: clean unchanged a23e088f, exit 1. Ruff and
  critical Pyright passed; six SDK test imports failed because that group needs
  its separately locked SDK interpreter. No dependency or gate was weakened.

The October 16 diagnostic .log files are now explicitly tracked and exempted
from newline conversion, matching their original index hashes. A regression
check rejects missing, untracked or hash-mismatched retained artifacts. These
repairs improve evidence portability; they do not change any test outcome.
Exact-current-commit full/backend/client/browser execution remains the next step.

Freshly fetched clean 51d2f59ed2c1553841fc24dda98689ffb26a0b7a passed **32**
focused-scope/paging tests (exit 0), with unchanged source fingerprints.
The earlier terminal-access limitation is historical and no longer applies here.

New configuration regressions reproduced **5 failures, 9 passes** before repair:
duplicate aliases, Boolean schema versions and malformed override symbols.
The first database regression run returned **1 failed, 64 passed** because a JSON
fixture was incorrectly embedded in SQL text; binding JSON as a parameter fixed
the test setup without changing its assertions. The repaired diagnostic returned
**71 passed, zero failures/skips**, including actual PostgreSQL migrations and
SQL checks plus test-wrapper child processes that mutate, delete or add source.
These runs used modified source on top of 51d2f59e and are explicitly diagnostics,
not acceptance of that Git commit. Frozen acceptance remains pending here.

All test children use sanitized local settings, no inherited service credentials,
disabled financial flags and owned localhost databases. Synthetic readiness rows
test the SQL boundary; they are not provider or broker certification.
The wrapper now records dirty state, command exit status and source identity,
supports --require-clean, and fails when a successful command changes the source.

Read-only Railway evidence confirms the API/public-web release mismatch, no
staging environment and a crashed historical observer. GitHub billing still
prevents required jobs from starting. No merge, deployment, production database
query, external billing/Telegram operation, broker call or permission change ran.
Retained observations and local receipts are under evidence/continuation-20261016/.

## Historical focused-universe implementation and CI retry — 16 October 2026

This continuation added a data-backed five-class candidate configuration at
`configs/focused_universe.json`, a fail-closed classifier/selector at
`core/focused_universe.py`, and an opt-in engine integration **after** managed,
pinned and discovered candidate merging, before profile ranking.
`FOCUSED_UNIVERSE_ENABLED` defaults to false. If enabled, the engine requires
an explicit staging/development/test environment. Production cannot activate
this unqualified experiment through a normal config flip.

The current candidate universe is **not provider-certified, broker-certified or
production active**; unsupported or misclassified instruments are excluded, and
historical trades/open-position management are not mutated. Full enterprise-wide
enforcement at new-order, Telegram, web, API and other signal entry points is
still missing. New pytest tests cover alias deduplication, whitelist limits,
empty/fallback rejection, staging-only activation and source-contract parity.
Their existence is not evidence they executed successfully.

A connector readback of seven files checked 31 structural and JSON contract
assertions: **31 passed, 0 failed**, without executing Python or importing the
application. This is static verification only. Existing retained local Python
evidence (3,984 passes) remains scoped to c411ebbb; it does not cover these
new commits.

Hosted GitHub Actions run 38932482649 was retried (attempt 2); both failing
jobs still have zero executed steps. Exact-head run 38943080448 also ended
with failed manifest and release-certification jobs, **zero steps executed**.
The documented billing-account restriction remains unresolved. No source-level
pytest, full build or hosted regression pass can be claimed for this head.

A read-only live website extraction on 16 October resolved `/` to `/app`
and showed the retained SignalRankAI trading workstation and session-restoration
screen. Direct `/login` returned HTTP 404. No authenticated session, order,
payment, Telegram operation, deployment or staging soak was exercised.

# Completion evidence

## Stage 1 continuation — 16 October 2026 (current user focus)

The 15 October user instruction narrowed the desired active universe to 10 preferred
core and up to 5 qualified optional instruments in each of five asset classes.
The candidate policy and explicit **NOT_IMPLEMENTED** status are preserved at
[current_scope_20261016.json](current_scope_20261016.json). The additional
`scripts/validate_current_scope.py` and
`tests/test_current_scope_handoff_20261016.py` guard this source contract,
including no implicit live authorization and continued management of existing
positions. The master contract, blockers and feature inventory were updated.

A connected-repository **static readback** of six committed files checked
24 policy/document assertions: **24 passed, 0 failed**. This checks source
integrity and link consistency only; it is **not** Python pytest execution,
runtime discovery enforcement, browser or live-broker testing. The preexisting
3,984-test report still refers only to c411ebbb, not these later changes.
Hosted CI and exact-head regression execution remain outstanding because of
the documented GitHub billing lock. No environment variables, trading
permissions, orders, production data or deployments were changed.

Latest integrated runtime candidate: `c411ebbb67d35fdad91d1281b667a7ee8272dd38`.
On 16 October 2026 the full local run passed **3,984 tests, zero failures,
errors, skips or unparsed batches**, across all 20 pytest batches and 12
additional checks. The checkout was clean and source identity remained unchanged.
This is local acceptance, not hosted CI or production certification.

Retained receipts, logs and failed diagnostics are indexed with content hashes
in [local-20261016/index.json](evidence/local-20261016/index.json). Receipts retain
their original SHA, command, environment, times, result and artifact path; the
index binds the retained copies. Do not add overlapping focused/full counts.

| Check | Actual result | Evidence and scope |
| --- | --- | --- |
| Complete Python suite | 3,984 passed; 0 failed/errors/skipped | [Full report](evidence/local-20261016/full-20261016/complete_system_test_report.json); clean c411ebbb; owned local PostgreSQL 17, financial switches disabled |
| Environment/schema/architecture/session/governance/secret checks, runtime snapshot, local Railway simulation, fanout and provider contracts | All 12 passed | Full-run logs; provider certification used mocks, never --live |
| Next production build and real browser/API/database | 10 scenario groups passed | [Browser result](evidence/local-20261016/next-browser-20261016/browser-results.json); c411ebbb; registration/consent, cookies/CSRF, persistent watchlists, refresh/logout, tenant/operator denial, 9 widths and both themes |
| Retained workspace mode | 8 scenario groups passed | [Legacy result](evidence/local-20261016/legacy-browser-20261016/browser-results.json); c411ebbb; login, deep links, PWA, callbacks, mutation no-replay and CSRF; 6 widths |
| Browser cleanup | Both passed | Respective cleanup.json: owned servers stopped, test databases dropped and temporary private keys removed |
| Android and iOS JS bundles | Both exported | [Export receipt](evidence/local-20261016/native-export-20261016.json); unchanged c411ebbb; no signed device installation claimed |
| Frontend tests | 63 passed; 0 failed/skipped | frontend-unit-frozen receipt at 2e94cae3; frontend bytes unchanged through c411ebbb |
| Mobile tests | 53 passed; 0 failed/skipped | mobile-unit-permitted-frozen receipt at 2e94cae3; mobile bytes unchanged through c411ebbb |
| Frontend lint and both clients' TypeScript | Passed | Retained lint/typecheck receipts; same unchanged client sources |
| Python runtime and market-data SDK audits | No known vulnerabilities reported | Retained pip-audit receipts, 15 October; unchanged lockfiles; not general security certification |
| Frontend dependency audit | No known vulnerabilities reported | Retained npm audit receipt, 15 October; unchanged lockfile |
| Mobile dependency audit | FAILED: 4 high rows; 0 critical | Expo/node-forge chain; [official advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv) lists no patched version; no suppression or unsafe downgrade |
| Foundation regression | 76 passed before integration; included in full suite | Consent/cancellation, migration preservation, universe paging, provider/ML behavior, evidence integrity and secret scanning |
| Integration failure repairs | 49 passed; included in full suite | MFA consent fixture, source-only scheduler ownership inspection and concrete routes |
| Hosted CI | BLOCKED_EXTERNAL | Retained GitHub billing-lock annotation: jobs never started; local checks do not replace hosted gates |
| Public site observation | / returns 200 JSON; /login 404; /app 200 HTML | [15 October observation](evidence/public-site-observation.json); no public Next cutover or deployment performed |

## Failures investigated

The earlier full-frozen diagnostic returned 3,981 passed and 3 failed; its source
changed during the run, so it cannot certify a frozen revision. Failures were a
pre-consent MFA fixture, a recursive source test counting separate ignored
worktrees, and stale governance hashes. The corrected complete run passed every
batch without retries. No acceptance threshold or safety assertion was disabled.

Initial sandbox Node subprocess failures, a leftover test-server compiler lock,
and a mistaken Expo web export request were environment/invocation failures.
Supported checks subsequently passed as recorded above.

The first real browser run found missing site attribution on recovered legal
pages. Commit 49d754599223f5000238a769d31f19210875d5f4 fixes all six pages; both
clean c411ebbb browser modes pass. Database-heavy tests exceeded the old
300-second harness bound; the final bounded allowance was 1,200 seconds, and
batch 1 completed in 480 seconds. The normal 25-second Railway startup check
passed without raising its own limit.

## Evidence integrity and limits

scripts/completion_matrix.py requires a repository-contained artifact with
matching hash, commit/environment/time/command/result/scope and source clauses,
zero exit code, positive passing count and zero failures/errors/skips before
accepting VERIFIED dispositions. Historical PASS labels are never promoted.
Unresolved source-clause acceptance remains explicit in the requirement matrix.

GitHub deployment/artifact metadata records inspection scope, not the contents
or validity of every historical artifact. No current authenticated production
audit, provider entitlement certification, broker lifecycle, real-money execution,
external notification/payment journey or staging soak is claimed. Later evidence
commits do not change the identity of the tested runtime candidate; they need
their own inventory/governance checks.

## Subsequent continuation — local execution constraints and DB-only shortlist

The owner authorized an **equivalent local verification path** instead of unavailable
GitHub Actions, but did not waive substantive safety, correctness, independent
review, deployment identity or broker/demo acceptance. This environment could
not fetch or clone the repository: `git ls-remote` returned
`Could not resolve host: github.com`. The GitHub connector permits remote
source reads and commits but does not expose the user's Codex working tree,
uncommitted edits, or a terminal. Vercel sandbox creation was independently
denied (403). **No exact-head full-project local pytest/build/DB/Telegram/broker
suite could be executed in this continuation.** Prior 3,984 Python passes are
not transferable to the current SHA.

Source audit found a focused-universe eligibility bypass: the experimental
staging selector was initially fed merged owner-managed, user-pinned and
discovered symbols, which are not equivalent to database/provider
qualifications. The branch now captures
`_focused_db_symbols` **before** `build_class_complete_universe` may add
unqualified provider-discovery fallbacks, then selects only from that stored
database-certified candidate snapshot. If DB discovery fails or the
universe source is not `database_registry`, it selects an empty active
scan set. All changes remain staging opt-in and default-disabled; order
routing is not certified. A regression source assertion was added. Actual
pytest execution remains pending.

Railway still has no separate staging environment in the connected project,
and production API/public-web use different older commit identities.
Do not merge or deploy until exact-head local verification, controlled
migration checks, permissions, demo fills, web/Telegram tests and operational
release gates genuinely pass.

