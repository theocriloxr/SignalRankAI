# Release blockers and exact continuation

## Continuation, 8 November 2026 (after the 13:39 deploy) — owner steps automated, plan decisions recorded (cloud session)

Production runs `38159361` since 13:39 UTC (backend, schema `0059_close_pending_terminal`) and 13:54 UTC (website), verified from the public `/readyz` and `/frontend-health`. `/readyz` reported `degraded` only for `outcome_to_ledger_mismatch` on ZECUSDT `66b151e6`, the outcome 0059 corrected. The ledger rows refresh when each recipient opens their results (5 → 1 within 15 minutes).

- **Owner steps now run by analytics (`services/post_deploy_maintenance.py`, new; `POST_DEPLOY_MAINTENANCE_ENABLED`).** Two minutes after start:
  - It re-reconciles the performance ledgers of users who hold a ledger row for an outcome corrected by migration 0059. This clears the readiness mismatch on every deploy, without waiting for users to open their results. Switch: `POST_DEPLOY_LEDGER_REFRESH`.
  - It runs `scripts/correct_stale_tick_shadow_labels.py` as a **dry run** once, for labels tracked between 5 Sep and 4 Nov 08:00 UTC. That is when the stale-tick fix `bec9a5f` went live; it is not today's deploy, which the 8 Nov evening handoff wrongly suggested. It pauses 0.5 s between id windows and stores the counts (`maintenance:stale_tick_relabel:v1:preview`). Switch: `POST_DEPLOY_STALE_TICK_RELABEL`.
  - Applying stays the owner's decision, as the owner asked (dry run first, then apply). The new owner-only Telegram command `/stale_tick_relabel` shows the counts; `/stale_tick_relabel preview` runs the dry run again; `/stale_tick_relabel apply` applies the audited correction (only after a dry run) and messages the result. A marker keeps the apply to once, and the script skips rows already corrected or tagged with their label source.
- **Deck strategies are gated by their own record (`STRUCTURE_SETUPS_MODE=auto`, the new default).** Every setup is recorded in shadow and also offered as a candidate. The engine's setup-evidence filter (`_segment_quarantine_gate`, fail-closed while the ML gate is advisory) refuses a setup until its measured TP1 rate's Wilson lower bound beats that plan's break-even. A setup with no record has a lower bound of 0 and is refused. This implements "live only once the record is good" per setup, with no manual switch. If `SEGMENT_QUARANTINE_ENABLED=0`, `auto` stays shadow-only. `shadow`, `live` and `off` still exist.
- **Plan decisions (owner asked the session to decide, 8 Nov):**
  1. Strategy ladders are **not** restored. The engine keeps publishing the strategy's final target as the plan's target (`engine/core.py`: `take_profit` before `targets`). Each card's setup record and the evidence filter were measured on this plan. A closer TP1 would raise break-even (for example from 36 % to about 57 % at 1.5R), so setups would be refused while their record still reflects the old plan.
  2. TP3 stays recorded at the full move to TP3. Cards show both that figure and the result with the 50 %/25 % closes. Single-target signals (ADX Trend) never record a TP3.

  Both are reversible on the owner's word.
- **Still owner-only (accounts or server shell):** `DEPLOYMENT_TELEGRAM_SEND_TEST=0` on the bot; the OpenAI key; Paystack channels, live key and webhook; the GitHub billing lock.
- **Tests (Linux, Python 3.11.18, owned PostgreSQL 16 at 0059):** `tests/test_post_deploy_maintenance_20261108.py` (3, one on PostgreSQL: the ledger-user query runs, the correction runs once and the marker makes a repeat skip); `tests/test_structure_setups_20261108.py` (7, including `auto` with and without the evidence filter).

## Continuation, 8 November 2026 (late night) — the strategy scorecard sees the whole 30-day window (cloud session)

- **Scorecard coverage.** `services/strategy_scorecard._load_rows` reads `decision_log` in id pages (`STRATEGY_SCORECARD_MAX_PAGES` × `STRATEGY_SCORECARD_PAGE_ROWS`, 400 × 5,000). Since 4 Nov, when the 30-day lookback held more ids than that budget, it kept only the newest ids: about 5 of the 30 days. With the same budget, `shadow_scan_pages` now reads the newest half of the pages contiguously and spreads the other half evenly over the rest of the lookback, so every part of the window feeds the per-setup hit rates. The rebuild log says `window_sampled … older_pages_sampled=N`, and `LAST_SCAN` carries the count. Mode (`shadow`), bounds, sample minimums and budget are unchanged. Also fixed: a lookback starting at id 0 was not reported as truncated (`if truncated` → `is not None`).
- **Tests (Linux, Python 3.11.18):** scorecard tests 16 passed, including `test_older_part_of_the_lookback_is_sampled_not_dropped`.

## Continuation, 8 November 2026 (night) — pegged tokens refused by the paper desk; news-gate warning after a host boot (cloud session)

- **Paper desk refuses pegged tokens.** The owner's screenshot shows an XAUTUSDT (tokenised gold) paper short. Since 1 Nov the engine excludes pegged tokens before scanning (`core.pegged_assets`), so that trade most likely predates the filter. As a last-line guard, `PaperTradingService` now records `pegged_asset_excluded` and opens nothing for a pegged token (quietly, no Telegram notice). PEPE, TRUMP and XSPCX are not pegged; they come from the server's trending discovery (`ASSET_DISCOVERY_MODE=auto`, top 15), which is the owner's configuration and was not changed.
- **News-gate warning suppressed after a host boot (fixed).** `services/economic_calendar.is_no_trade_zone_sync` throttled its "news gate unavailable" warning from `_LAST_GATE_WARNING = 0.0`, compared against `time.monotonic()` (seconds since boot). For ten minutes after a host or container boot the first warning was therefore swallowed: the silent failure the warning exists to prevent. It is now `None` (never warned). The test failed only on a host booted less than ten minutes earlier; it now sets `None` too.
- **Tests (Linux, Python 3.11.18, owned PostgreSQL 16 at 0059):** paper tests 249 passed; `tests/test_master_p0_postgres_integration.py` 66 passed; `tests/test_live_candles_and_paper_desk_20261108.py` 4 passed; economic-calendar and owner-decision tests 13 passed. Full suite before these two fixes: 4,448 passed, 215 skipped, 2 failed (this calendar test, and governance freshness, regenerated in this commit).

## Continuation, 8 November 2026 (evening) — paper desk, sign-up and sign-in, icons, live candles, paper plan mode, strategies from the owner's deck (cloud session)

Commits `b8b6f82` and this one on `claude/pensive-fermat-hju9hw` (not merged into the deploy branch). The evidence is the owner's paper-desk screenshot (circled: cash, equity, open positions, realised P/L, and the "Open positions" table) and an archive of two PDFs: 466 photos of annotated TradingView charts (XAUUSD and Deriv synthetic indices, 5m/15m) with MT5 position lists. Production logs were not available; reachable logs were checked instead: test-suite warnings, a local start of the web app, and a production Next build (no warnings, no browser console errors).

- **Paper desk.** All positions were listed under "Open positions" with their open P/L, so closed trades showed USD 0.00. Open positions and closed trades are now separate tables; closed trades show exit price (from the close ledger entry), result, R, fees, reason and time. The cards show starting balance, equity, return, cash, realised and open P/L, the number open, and closed trades won, with a line showing how equity reconciles (the screenshot's figures do: 10,000 + 373.29 − 5.72 − the open entry fee ≈ 10,366.29).
- **Sign-up.** "Create a free account" opened the Sign in tab, so new visitors filled in the sign-in form. Those links now open Create account (`/login?mode=register`), and the header offers "Create account". The form shows the server's real password rule (10+ characters, three of lowercase, uppercase, number, symbol) as a live checklist, and the server's reason for a refusal (e.g. email already registered) instead of a generic error.
- **Sign-in.** `platform_csrf_middleware` refused login and registration from anyone holding a leftover session cookie without a matching `sr_csrf`, although its docstring exempted these endpoints. They are now exempt when Origin/Referer is same-site; foreign origins and every other cookie mutation still need the token. Verified through FastAPI on PostgreSQL: registration 201, and sign-in with a stale cookie 200 (it was 403).
- **Show/hide password** on every password field (sign-in, sign-up, recovery).
- **Icons.** `/favicon.ico` was the stock Next.js icon. `favicon.ico` (16/32/48), 32/192/512 PNGs and an Apple touch icon are now rendered from the real SignalRank mark (`public/brand/icon.svg`); the unused create-next-app SVGs are removed.
- **Live candles on the signal page.** New read-only `GET /signals/{id}/candles?after_ms=` (same delivery proof as the detail view) returns newer and still-forming bars, the tracker's last price and the trade status. The chart polls it (15 s for 1–15m, up to 60 s otherwise), pauses in hidden tabs, stops when the trade closes, and draws a "Now" price line. `openapi.json` and `api.d.ts` have additions only; parity matrix regenerated.
- **Paper trades follow the broker process (`PLAN` target mode, additive).** A broker position's stop moves to entry at TP1 (`engine/trade_manager`). A PLAN paper position now runs the published plan the same way: 50 % closed at TP1 and the stop moved to entry, 25 % at TP2, the rest at the last target or the protected stop (exit reason `BE`). Every partial close pays its fee, releases its share of reserved cash and is written to the ledger as `POSITION_PARTIAL_CLOSE`; the final R uses the risk at entry. TP1/TP2/TP3 modes are unchanged. It is available in web settings ("Follow the plan, like a broker position") and `/paper_settings target plan`. Single-target signals close in full at that target, as a broker take-profit order would.
- **Strategies from the owner's deck (`strategies/structure_setups.py`, new, shadow only).** Zone flip retest, trendline break-retest, and channel/triangle break, built from swing pivots. Stops sit just beyond the structure; targets are the next swings or measured moves at least 1R away (closer levels are skipped, never invented). `STRUCTURE_SETUPS_MODE=shadow` (default) records each setup for the shadow tracker, so the setup-evidence filter measures it before it can reach a user; `live` returns them as candidates that still pass every gate; `off` disables them. Nothing existing changed.
- **Warnings.** A module-wide asyncio mark on a sync test was removed. The remaining test warning comes from a third-party test client (`httpx` with Starlette).
- **Tests (Linux, Python 3.11.18, owned PostgreSQL 16 at 0059; Node 22 with npm 11.10):** new `tests/test_auth_csrf_and_signup_20261108.py` (4), `tests/test_live_candles_and_paper_desk_20261108.py` (3, one on PostgreSQL), `tests/test_structure_setups_20261108.py` (7), and in `tests/test_master_p0_postgres_integration.py` the PLAN mode test, long and short. That file passed in full (66) against PostgreSQL with `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`. Full suite: 4,447 passed, 215 skipped, 2 failed (the parity matrix and governance freshness, both regenerated in this commit). Frontend: `next build` clean, `tsc`/ESLint clean, 81 + 41 node tests.
- **Owner steps:** merge into the deploy branch; switch paper accounts to `PLAN` if wanted; leave `STRUCTURE_SETUPS_MODE` at `shadow` until the setup evidence shows a positive record.

## Continuation, 8 November 2026 (later) — owner findings: trade status, closed P/L, late entries, money calculator (cloud session)

Owner findings, verbatim in substance: (1) a trade whose entry triggered still shows "waiting for entry"; (2) closed signals do not show the trade's balance or P/L; (3) some entries arrive late, so users cannot take the trade; (4) the calculator does not calculate actual profit against the R/R. The owner also referred to a strategy PDF; it did not reach this session (no attachment, nothing on disk, no recent PDF in the connected Google Drive), so nothing from it is implemented yet. All changes are additions. No existing outcome rule, gate or threshold changed.

- **(1) Status from the lifecycle (`services/trade_status.py`, new).** The web lists read `outcomes.status`, a projection that stays `pending` after entry while `signal_lifecycles.state` is `ACTIVE_TRADE`/`TP1_HIT`. The signal feed, professional feed and elite feed now join `signal_lifecycles`; `_present_signal_for_tier` adds `trade_status` (lifecycle first, outcome row as fallback), and `WorkspaceLive.tsx` shows its label. The Telegram position view no longer guesses "Awaiting entry" from price distance, and no longer reports a `pending` outcome row as a completed outcome; it shows the same status line. Verified on owned PostgreSQL: a signal with a `pending` outcome and an `ACTIVE_TRADE` lifecycle now reads "Entry triggered — trade open" in the feed, the professional feed and the detail view.
- **(2) Result on every closed or partly closed signal.** `trade_status` carries realized R, the price move and the result per $100 risked. While a trade is open after TP1 it also carries the R banked by the planned close and the share still open. Missed entries say there was no position and no P/L. The web card shows these as "Result" or "Banked so far".
- **(3) Late entries.** When the card is sent and price is already 0.25R or more past entry toward TP1, the card says how far, gives the R/R from the current price, and suggests a limit order at entry: the tracker waits for an entry touch until the signal expires. Delivery latency itself was not measured: production logs were not available to this session.
- **(4) Money calculator (`engine.signal_calculations.calculate_money_plan`, new).** From the card's size, or from balance × risk %, it gives the amount at risk, the position value, profit if fully closed at each target, and money for each plan path (stop, TPn then entry, TP3 with the planned closes) using `core.partial_exit_accounting`. Fees and slippage are not included, and the card says so. `format_enhanced_signal_data` adds it as `money_plan` (existing keys unchanged), and Premium/VIP cards show it. BCHUSDT check: 32.47 units → $50.00 at risk, position value $8,934.77, stop −$50.00, TP1 then entry +$89.71, all closed at TP1 +$179.41.
- **Tests (Linux, Python 3.11.18, owned PostgreSQL 16 at 0059; frontend on Node 22 with npm 11.10):** `tests/test_trade_status_and_money_plan_20261108.py` (8); frontend `tsc --noEmit` clean, ESLint clean, transport tests 81 passed, presentation tests 41 passed. Full Python suite: 4,434 passed, 213 skipped, 1 failed (governance freshness, regenerated in this commit).

## Continuation, 8 November 2026 — the owner's 4–6 Nov signals: card math, outcome scans, Engine Pulse, lifecycle messages (cloud session)

Commits `d0b25ce`, `09f07e1` and this one on `claude/pensive-fermat-hju9hw` (after `8b8c6bc`). Not merged into the deploy branch. The evidence is the owner's Telegram transcript for 4–6 Nov (BCHUSDT, LINKUSDT, SUIUSDT 5m ADX Trend VIP signals, ZECUSDT paper trades, three hourly Engine Pulses); production was not read.

- **Cards invented TP2/TP3 (`d0b25ce`).** The SUIUSDT card (entry 0.8976, stop 0.8921) showed TP1 0.91733, TP2 0.93707 "close 25 %", TP3 0.95680, "TP3 R:R 1:10.76" and "+6.60 % to final target". TP2 and TP3 were made up by `_build_tp_fallbacks` (2× and 3× the TP1 distance). The signal stores one target, the tracker followed only 0.917334, and the trade was booked at +1.79R (50 % at TP1, the rest at the protected stop) although price reached 0.9563. Premium and VIP cards now show only the real targets and a "Plan result" line computed by `core.partial_exit_accounting`: stop first −1R, TPn then stop at entry, and TP3 with the planned closes, alongside what the ledger records for TP3. With fewer than three targets they also say what happens to the remainder, and show the R/R to TP1 from the current price when the card is sent late (or that price is already past the target or stop).
- **Why these signals have one target (owner decision, not changed).** `strategies/dynamic_targets.calculate_dynamic_targets` returns a 3-level `tp_levels` but sets `take_profit` to the last level only. `engine/core.py` takes `sig.get("take_profit") or sig.get("targets")`, so ADX Trend (and every strategy using it) publishes its final target as the only target. Restoring the ladder would move TP1 much closer (≈1R before the stop is adjusted), change every setup's break-even, and change what the setup-evidence filter lets through. The ledger also records a TP3 at the full move to TP3, while a user following the 50 %/25 %/runner plan earns less. Both need the owner's decision.
- **"Entry Not Triggered" 5 minutes after delivery (`d0b25ce`).** The bot's `compute_outcomes_best_effort` (scheduled when the bot owns outcomes) wrote `missed` whenever the bars since creation had not touched entry. It now waits for `expires_at` (fallback 24 h). The same scan now uses only the signal's own timeframe, moves the stop to entry after TP1 (a pullback is `partial_win_be` at the planned partial R, not −1R), stops at TP3, and books no R for missed or invalidated entries.
- **Engine Pulse reported lifetime counters as "trailing 1h" (`09f07e1`).** `compute_engine_health` passed a timezone-aware `since` to `timestamp without time zone` columns. asyncpg refuses that, so every window query failed (logged at debug), and the pulse showed the engine's lifetime counters (`ml: 736224` for three days) and the latest cycle's 5 assets as "Decision rows evaluated: 5, Unaccounted: 5". `since` is now naive UTC, the reads are also bounded by primary key, failures log at warning, and any fallback is labelled. The shadow lines follow the 3 Nov labels. The same aware-cutoff bug in `/outcome` is fixed.
- **Telegram messages (`09f07e1`, this commit).**
  - A card reopened from a lifecycle message (SUIUSDT at 14:53 and 14:54, after TP1) now starts with its current state ("TP1 already hit; the stop is protected at entry. This is not a new entry.").
  - "Paper Trade Not Opened — auto trade disabled" is no longer sent after each signal to users who switched automatic entries off.
  - The TP retrace warning is measured against the protected stop at entry, and is not sent once that stop has been crossed. On LINKUSDT it fired at 10.859, through both stops.
  - The protected-exit message says "Exit: protected stop at entry", and shows a market price only when one was observed (it showed the entry 11.069 as "Observed").
  - The local fallback review is labelled "Rule check (AI reviewer unavailable)" instead of "Local AI fallback".
- No threshold, gate, scorecard mode or bound, kill switch, execution, payout or billing setting changed.
- **Tests (Linux, Python 3.11.18 venv from `requirements.txt`, owned PostgreSQL 16 `signalrank_test` at 0059; not CI, staging or production):** `tests/test_signal_card_real_plan_math_20261108.py` (7), `tests/test_legacy_outcome_scan_plan_20261108.py` (5), `tests/test_admin_pulse_window_20261108.py` (3; on PostgreSQL 40 window rows counted, a 5 h old row excluded, nothing unaccounted), `tests/test_lifecycle_messages_truth_20261108.py` (4). Full suite (`pytest tests --ignore=tests/browser`, `SIGNALRANK_TEST_PG_DSN` set): 4,425 passed, 213 skipped, 2 failed. The failures were a test that pinned the old "Local AI" label (updated) and governance freshness (regenerated in this commit).
- **Owner steps:**
  1. Review and merge `claude/pensive-fermat-hju9hw` into the deploy branch.
  2. After that deploy, dry-run `scripts/correct_stale_tick_shadow_labels.py` (6 Nov entry), then run it with `--apply`.
  3. Decide the two plan questions above.
  4. Still open: `DEPLOYMENT_TELEGRAM_SEND_TEST=0`, the OpenAI key, Paystack, the GitHub billing lock.

## Continuation, 6 November 2026 — closed outcomes left at `pending`, shadow labels from July prices (cloud session)

Commits on `claude/pensive-fermat-hju9hw`, branched from `feat/frontend-rebuild-and-stage1-hardening` at `d9c58ba`. **Not pushed to the deploy branch**: that branch auto-deploys to the production server, so the owner merges after review. Production was not read in this session: Railway's SignalRank services are stopped since the 29 Oct cutover, the server is not reachable from here, and attaching the private ops repository (daily reports) was refused. The work is the open list of the 4 Nov daily review. GitHub Actions still fails at 0 steps in 2 s on every push (billing lock, BLOCKED_EXTERNAL; not a code failure).

- **Migration `0059_close_pending_terminal` (data only).** `ca78f6f` stopped new closed outcomes keeping a projection's `canonical_outcome='pending'`, but the rows already written that way (ZECUSDT 5m `66b151e6`, delivered to 5 users, stop hit 4 Nov 04:25) still counted as open in `services/performance_ledger`. The migration gives every closed row whose canonical outcome is `pending` or empty the result `upsert_outcome` now derives (tp/tp3/win → win; sl/loss/stop → loss, or partial_win when `meta.tp_hit_index` > 0; partial_win/partial_win_be → partial_win; time_stop, missed_entry, expired keep their name), as an audited correction under `trg_terminal_outcome_finality` (`corrected_by=migration_0059_close_pending_terminal`, the previous value named in `correction_reason`). Status, R, percent and inclusion are unchanged; open, `pending` and `tp1`/`tp2` rows are untouched. Alembic head references bumped to 0059.
- **Shadow labels record their source.** `engine/shadow_outcome_worker` stores `meta.outcome_label_source` (`candles` or `live_price`) on `decision_log` and `ml_shadow_predictions`. Before this, a label decided by a July `market_ticks` price (fixed for new rows in `bec9a5f`) could not be told apart from a candle-path label. The candle rule is now the module-level `label_from_candles` (unchanged behaviour).
- **`scripts/correct_stale_tick_shadow_labels.py` (owner-run, dry run by default).** Re-labels rows tracked in `[--since, --until)` for symbols Binance does not list, from stored `market_candles`, with the tracker's own rule: a terminal candle label is kept or written; no candle coverage or no barrier reached → `unverifiable` (excluded by every consumer). Each change keeps the previous label and `shadow_r` in `meta.label_correction`; linked `ml_shadow_predictions` rows get the same label; already-corrected or source-tagged rows are skipped (idempotent). `--until` is the time production first ran `bec9a5f`. Nothing was run against production.
- No threshold, gate, scorecard mode or bound, kill switch, execution, payout or billing setting changed.
- **Tests (Linux, Python 3.11.18 venv from `requirements.txt`, owned PostgreSQL 16 `signalrank_test` migrated empty → 0059; not CI, staging or production):** migration seeded with 7 outcomes under the finality trigger (a direct canonical change was refused by the trigger): upgrade corrected 4 (sl→loss, sl with TP1→partial_win, tp3 with empty→win, expired with NULL→expired), left loss/pending/tp1 untouched; downgrade restored `pending` on the 2 rows that had it; re-upgrade stable. `tests/test_stale_tick_label_correction_20261106.py` (10, including the script end to end on PostgreSQL: dry run counts, apply writes 3 rows and the linked prediction, Binance and source-tagged rows untouched, re-run scans 0); shadow tracker test files 36 passed, 3 skipped. Full suite: see the line below.
- **Owner steps:** review and merge this branch into the deploy branch (0059 then runs through `controlled_migrate.py` after the predeploy backup); then on the server, dry run first:
  `python scripts/correct_stale_tick_shadow_labels.py --until <first bec9a5f deploy time, UTC>`, and with the counts accepted, the same command with `--apply`. Still open from earlier days: `DEPLOYMENT_TELEGRAM_SEND_TEST=0` on the bot, the OpenAI key, Paystack channels/live key/webhook (`docs/operations/OWNER_STEPS_20261103.md`), the scorecard's page budget (newest ~5 days of shadow rows), and the GitHub billing lock.

## Continuation, 3 November 2026 (night) — the truth on every card and in every results view, forex providers, owner steps (desktop session)

Owner: "let it still send signals even when it is not yet on a minimum of 82% win rate, I just want that to be the truth not a brag", plus a full check that every figure matches the database.

- **There is no 82 % gate.** The evidence filter only refuses a setup whose measured TP1 rate (lower bound) is below its own break-even. That is unchanged.
  - Shadow labels written after `e196aacc` were checked on production. 3,587 of 17,733 setups reached their first target (20 %).
  - Many candidates carry a single target that the label names `tp3`, which is why `tp2` never appears; wins are still counted as TP1-or-better.
  - Those setups do lose, so the filter is right to hold them.
- **The real record on every signal.** Premium and VIP cards now carry, for example: "Setup record (60 days): 663 of 1,295 similar setups reached TP1 (51 %). This plan breaks even at 41 %." It is shown whatever the numbers are.
  - Signals delivered from the database get the record from the current snapshot (`segment_evidence.attach_records`). Without current evidence nothing is shown.
  - The web signal detail returns the same record as `setup_record`.
- **Figures that were not true, removed or corrected:**
  - "TP1 33 % / TP2 33 % / TP3 34 %" (or 50/50) on cards now shows the published exit plan from `planned_exit_fractions()`: 50 % / 25 % / runner.
  - "Trade Health %" and "TP1 by 24h %" are no longer shown: they were weighted heuristics with assumed defaults (60/55) for missing inputs.
  - "Expected Profit / Expected Loss" are renamed "Move to final target / Move to stop": they are price distances, not expectations.
  - "Signal Quality Score" now reads "Engine score … (ranks setups; not a chance of winning)", and the "high-conviction / strong setup" wording is gone: the score did not predict TP1 (AUC 0.489).
- **One source for a user's results.**
  - `/stats` and `/mystats` counted any `tp*` as a win over all outcome rows (open, missed and expired included), ignored the audited ledger exclusions (0058) and could count a signal twice.
  - The website, `/stats` and `/mystats` now read `services.performance_ledger.ledger_summary`: win rate is TP3 vs SL, as in `/performance`; partial wins and breakevens are listed separately; excluded rows stay out.
  - `/mystats` keeps broker executions and broker P&L as broker figures.
- **Forex data.**
  - Every forex fetch spent both attempts on Twelve Data (in cooldown, 524 in 30 min) and Tiingo (HTTP 429, 340), so yfinance, the configured preferred provider, never ran.
  - A provider in a recorded rate-limit cooldown no longer uses an attempt.
  - Tiingo now records a 15-minute cooldown on 429 (`TIINGO_RATE_LIMIT_COOLDOWN_SECONDS`), for its hourly quota.
- **Indices.** After the owner set `INDEX_MARKET_DATA_PROVIDERS=yfinance,twelvedata,polygon` and `INDEX_TIMEFRAMES=5m,15m,1h,4h,24h`, US500 and NAS100 received yfinance candles on every timeframe at 19:47 UTC, and indices are no longer scanned on 1m.
- **Owner-only steps** are in `docs/operations/OWNER_STEPS_20261103.md`:
  - `DEPLOYMENT_TELEGRAM_SEND_TEST=0` on the bot (this session may not write to the server);
  - the OpenAI key;
  - Paystack payment channels, live key and webhook URL.
- **NATA** has its own session and repository (`theocriloxr/NATA-Lagos-Production`), with a fix-and-audit brief.
- **Tests:** `tests/test_setup_record_display_20261103.py` (6) and `tests/test_results_consistency_20261103.py` (1), the latter on real PostgreSQL; the cooldown tests are in `tests/test_index_provider_attempts_20261103.py` (11 in total).
  - Full suite (Windows 11, Python 3.13.7, PostgreSQL 17 migrated empty → 0058): 4,573 passed, 2 failed (the environmental isolated-metadata test, and governance freshness, regenerated in this commit).

## Continuation, 3 November 2026 (evening) — advisory signals reach subscribers, volatility stops, index provider attempts (desktop session)

Parent `f7fd8a17`. Production evidence was read with read-only SQL and log greps over SSH on 3 Nov, 18:00–19:30 UTC.

- **Why the two 3 Nov signals were never delivered.** HYPEUSDT 1h short (`6c39bd86`, score 62.8) and BTCUSDT 5m long (`b0f857a4`, score 65.0) are both `ml_advisory_mode`, and neither has a `signal_deliveries` row. Reproduced end to end on PostgreSQL with `dispatch_signals_async`, three filters refused them before anything was reserved:
  - `recovery_delivery_allowed` limits every `ml_recovery_mode` signal to owner/admin unless `ML_RECOVERY_DELIVERY_AUDIENCE=all`, which is not set on production;
  - every tier minimum score (80 for Free/Premium/VIP) refused them;
  - the profile floor (`USER_PROFILE_BASE_MIN_SIGNAL_SCORE` 75 plus the risk boost) and the opportunity ranker's technical floor (`PERSONALIZED_BASE_MIN_SCORE` 75) dropped them as well.
- **Fix.** `core.signal_quality_gate.meets_tier_score` follows `QUALITY_SCORE_GATE_MODE`.
  - In the default advisory mode, these system score floors record but do not refuse. This covers the tier manager, both formatters, delivery authorization, the web fan-out, the profile floor and the ranker.
  - A minimum score a user chose themselves still applies.
  - ML-advisory signals reach every tier. Starvation-recovery signals stay owner/admin only.
  - A Premium or VIP card below the tier minimum says PAPER ONLY.
  - Live execution still refuses these signals, as before. `enforce` restores every floor.
  - Tests: `tests/test_advisory_signal_delivery_20261103.py` (4). The real dispatch path reserves and sends an advisory signal with score 63 marked PAPER ONLY; with `enforce`, a signal scoring 79 is not sent. The tier-gate tests in `tests/test_single_service_defaults.py` now pin `enforce`, plus one new test for the advisory default.
- **Volatility strategies (`strategies/volatility.py`).** ATR Breakout, BB Width Volatility and Keltner Volatility put the stop at the bar's low, so a bar closing at its low gave entry == stop.
  - The ATR repair's level rule now lives in `core/atr_levels.py` and is shared by the strategies and `SignalController._atr_repair_levels`, with unchanged repair behaviour.
  - The strategies apply it at the source when the low is missing, on the wrong side, or within 0.25 ATR of entry. Normal levels (low stop, 2R target) are unchanged, and no levels are emitted without an ATR.
  - Tests: `tests/test_volatility_strategy_levels_20261103.py` (8); the 8 repair tests still pass.
- **ADX Trend wide stops are not a level bug.** 3,011 of 3,028 `SL too wide` ADX Trend rejections in 24 h are on **1d** (median 9.7%, LTC/SUI/AVAX/LINK). The daily ATR is 4–6%, so a 2 ATR stop is 8–12%, and validation refuses anything over 8% for crypto. The levels were left as they are; the options are for the owner.
- **Indices (`data/fetcher.py`).**
  - On production, `INDEX_MARKET_DATA_PROVIDERS=fmp,twelvedata,polygon,alphavantage,yfinance` sets a strict order. FMP and Alpha Vantage have no index candle connector, which leaves twelvedata → polygon → yfinance.
  - Only 2 attempts are allowed per timeframe, and they went to Twelve Data (in rate-limit cooldown) and Polygon. Polygon was tried even for the seven indices it is mapped to `None` for, so yfinance, the configured preferred index provider, was never tried.
  - Now a provider with no symbol for the asset does not use an attempt, in the async and sync paths. GER40, UK100, JP225, FRA40, EU50, AUS200 and HK50 now reach yfinance; yfinance is installed on production and returns 200-candle series for other assets there.
  - US500, NAS100 and US30 have real Polygon symbols (`I:SPX` etc.), which need a Polygon indices plan.
  - **Server env needed (owner or server session):** `INDEX_MARKET_DATA_PROVIDERS=yfinance,twelvedata,polygon`, and `INDEX_TIMEFRAMES=5m,15m,1h,4h,1d` (it is unset, so indices fall back to the global list, which includes 1m).
  - Tests: `tests/test_index_provider_attempts_20261103.py` (9).
- **Setup evidence after the re-labelling (snapshot computed 18:32 UTC, 95 setups).**
  - At the published plan (TP1 close 0.5), the setups whose lower bound is highest are: ATR Breakout 1m long (1,295, lower bound 48.9%) and 4h long (117, 48.8%); MACD Momentum 5m long (112, 44.9%); ADX Trend 1m short (3,296, 43.5%); EMA Trend 1m short (20,104, 43.3%) and long (18,513, 41.9%). Each passes when its TP1 reward/risk exceeds 2.1–2.8.
  - Recent candidates are mostly EMA/ADX Trend on 5m–4h, at lower bounds of 20–31% against break-evens of 35–42%. Examples: EMA Trend 15m short 2,361/10,917; ADX Trend 15m short 647/2,173. These are mostly WTI, BRENT, XAU and XAG, which the 3 Nov report also found losing.
  - No signal has been issued since 10:13 UTC: in the 30 minutes read, 55 candidates passed the advisory ML step, and stop width, confluence and the evidence filter refused them all.
  - Labels from the last 6 h: sl 26,476, tp3 3,685, tp1 553, ambiguous 87, tp2 0. Rows labelled before `974e99a9` keep the TP3-before-SL bias until they leave the 60-day window, which understates TP1 rates for most setups.
  - Proposals for the owner, nothing changed: re-label recent rows with the new rule, or count only rows labelled after `974e99a9`. Thresholds, confidence level, gate modes and scorecard mode/bounds are unchanged.
- **Frontend look (owner request, 3 Nov: the site looked machine-made).**
  - The near-black and neon-green theme, glow and grid backgrounds, pill badges, accent-coloured slogan headlines, icon-tile cards and the 01–04 stepper are gone.
  - The tokens are now warm paper and ink by default, plus a warm charcoal dark theme, both meeting the AA contrast test. Headings use a system serif and figures use tabular numbers; there is no web-font download.
  - The home page was rewritten in plain words: what we send, how the 60-day evidence rule decides, what you get, the markets we cover, and what we won't pretend. It shows one example ticket labelled "Example", not a live signal.
  - The sign-in page has the same treatment. Section labels are no longer all-caps monospace tags.
  - `SignalLifecycleExperience` is removed. The design contract tests now pin the example label, the links, the absence of write calls and fictitious metrics, and the evidence-rule copy.
  - Checks: `tsc`, `eslint`, `test:presentation` (41) and `test:transport` (81) pass. The local production build was checked at 1280 px and 375 px in the light and dark themes, with no horizontal overflow.

- **Workspace look (same owner request; commit `a9c36c15`, not pushed, not deployed).**
  - The signed-in pages now use the same paper-and-ink tokens, serif headings, sentence-case labels and small radii as the public site. Icon tiles, the hero glow, the topbar blur, icons in notices, stats, empty states and sidebar links, and all-caps or slash-joined labels are gone.
  - Signals are shown as tickets. Each one shows the setup's 60-day record (wins of resolved trades reaching TP1) when the signal carries `segment_evidence`, and the break-even rate it needs. Advisory and recovery signals (`ml_recovery_mode`) are tagged PAPER ONLY. The detail page adds a "Why this was sent" panel with the record, the cautious (Wilson lower-bound) estimate and the break-even rate.
  - **Gap, not fixed here:** the engine computes `segment_evidence` but does not store it (the `signals` table has no column for it), so no stored signal carries its record. The page says "Setup record not attached" and works out the break-even rate from the API's `rr_tp1` as `1/(1+0.5*rr_tp1)`. The 0.5 is the default `SIGNAL_TP1_CLOSE_FRACTION`, the half-at-TP1 plan the home page publishes. Persisting and exposing the record needs a migration and an API change.
  - Performance shows the closed count with an outcome bar, plain rate labels and a small-sample note (under 30 closed overall, under 10 per instrument row). The paper desk, research, overview, operations and status copy is rewritten in plain words; the typed confirmation phrases are unchanged.
  - There is no strategy builder or backtest route in the web app or the platform API (only the admin strategy-count leaderboard). The Research page says so instead of implying one.
  - Every data fetch, authorization check and contract-pinned string is unchanged. Checks at `a9c36c15` (Windows 11, Node, local only): `tsc`, `eslint`, `test:presentation` (41 passed) and `test:transport` (81 passed). `next build` passed. The owned local stack (API on 127.0.0.1:8443 against the owned PostgreSQL `signalrank_research_browser_test_local27`, all money and execution flags off; 4 synthetic `SYN-UI-*` signals, one advisory) was checked: signals, signal detail, performance, paper, research and overview at 1280 px and 375 px in light and dark. No horizontal overflow and no console errors. Not CI, staging or production.

- **Tests (Windows 11, Python 3.13.7, PostgreSQL 17 migrated empty → 0058; not CI, staging or production):** full suite 4565 passed, 1 failed (the 1 failure is environmental: isolated python -I cannot import the user-site alembic).

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
- Production promotion was requested in chat on 27 Oct without the `PROMOTE_TO_PRODUCTION` phrase or the prerequisites in [PRODUCTION_PROMOTION_PLAN_20261024.md](PRODUCTION_PROMOTION_PLAN_20261024.md) (backup evidence, `EXPECTED_RELEASE_COMMIT` on every service, guarded `0054`/`0055` migration). Not executed.

## Continuation, 24 October 2026 — frontend rebuild, live readiness finding, independent audit

Branch `feat/frontend-rebuild-and-stage1-hardening` (from `393f3d88`; commits `7946fa25`, `840abd90`, `801780d4`, `7a63d5ac`, `8a7d3e3b` and this documentation commit). Stage 1 and release remain NO-GO; nothing was merged, deployed or migrated, and no financial permission changed.

- Web frontend rebuilt on a new design system; billing (server-priced Paystack checkout, verified confirmation, auto-renew cancel, refund review) and signal feedback wired to existing APIs. Local evidence: tsc, eslint, `next build`, 98 node tests at the time of commit; 61/61 pre-rebuild API calls and 11/11 routes retained (`frontend/scripts/api-baseline.test.mjs`).
- Focused-universe admission now guards both signal persistence paths and the MT5/Bybit execution chokepoints (no-op unless enabled in staging). HTTP 451 classified as `REGION_RESTRICTED`; Binance region blocks logged and backed off.
- Live read-only `/readyz` (deployed `9865a3d1`) returns 503: only `engine_runtime` fails — the `engine:last_cycle` heartbeat is absent, so the production engine is not cycling (Engine Pulse: 0 signals in window). Probe now reports `engine_heartbeat_missing`. Root cause needs Railway logs (blocked: access). Production DB is at `0053`; repository head `0055`.
- New owner source `message.txt` (SHA-256 `b78374d0…`) consolidated privately into 287 requirement IDs; hashes and anchors only in `evidence/continuation-20261024/source_intake.json`.
- Full Python suite at clean commit `e9b2b368` on a local PostgreSQL 16.2 database migrated from empty to `0055`: **4,098 passed, 0 failed, 1 skipped** (pyarrow not installed); multi-user isolation suite 5/5. Three pre-existing test portability/isolation defects fixed. Local only; GitHub Actions remains billing-locked. Limits in the audit §8.

Full details, classifications and information gaps: [INDEPENDENT_ACCEPTANCE_AUDIT_20261024.md](INDEPENDENT_ACCEPTANCE_AUDIT_20261024.md).

## Stage 0 safe local Git and historical forensics, 22–23 October 2026

The exact observed source is e01e7c41f49a3e35335b00edc2de97367aa2dade. Evidence: [Stage 0 forensics index](evidence/continuation-20261022/index.json). Release remains **NO-GO**.

Stage 0 forensics passed all local checks. Branch audit across 247 refs confirms 118 unique commits across 28 divergent refs, with 0 missing and 0 moved heads compared to `branch_dispositions.json`. Migration head is single: `0055_user_renewal_default`. 18 worktrees discovered; 17 clean, 1 dirty (`.pytest-tmp/release-ci-closure-20261007`) preserved untouched. Draft PR #201 remains OPEN under active ruleset 24410166; CI is blocked external due to GitHub billing lock. Live public routes (`https://www.signalrank.criloxsolutions.com`) confirm `/login` and `/pricing` 404, while `/` serves 200 JSON and `/app` serves 200 HTML workstation. Railway CLI session is expired, blocking fresh authenticated control plane re-verification. All 5 release governance checks pass with 0 drift.


## Correction verification closed at local scope, 18 October 2026

The exact tested source is 393f3d88d6018d01c3f04234cc9c44b23a5de8fc. Evidence: [correction index](evidence/continuation-20261018/correction-393f3d88/index.json). The receipt-overwrite defect and strict HTML parse failures are locally resolved: 4,080 clean full-suite passes, a complete zero-finding/zero-error OpenGrep scan, and a passing legacy browser drill with owned-resource cleanup.

Release remains **NO-GO**. The mobile dependency audit still reports four high-severity rows in the Expo/node-forge chain. Stage 1 source reconciliation remains incomplete: 13 reviewed dispositions and 26,874 unresolved applicability/acceptance rows. Focused-universe provider qualification and cross-path enforcement are unfinished local work.

Hosted CI remains unavailable/failed at the prior remote head; independent review, isolated staging, broker-demo/provider/payment/Telegram evidence, native device coverage, restore/rollback and soak gates remain unsatisfied. No deployment or financial permission change is authorized.


## Updated local acceptance, 18 October 2026

The exact tested source is 2ee0a918d915549f7f5ce59d59f0a8a07d2202a9. Evidence: [frozen run index](evidence/continuation-20261018/frozen-2ee0a918/index.json). Stage 1 and release remain NO-GO.

The stale generated-governance failure is resolved: full local system and both browser modes pass. The strict scan revealed two HTML parse failures; escaped text is awaiting a frozen rescan. The evidence wrapper correction also awaits frozen regression acceptance. Mobile dependency audit remains red.

Source reconciliation and focused-universe cross-path/provider qualification remain executable local work, not external blockers. Nine additional source-truth seeds were reviewed with explicit gaps (13 total); remaining applicability and acceptance are unresolved. The fresh branch snapshot has 247 refs and 118 unique unmatched commits requiring comparison with prior dispositions, not automatic merging.

GitHub requires independent last-push approval plus manifest/release-certification; hosted Actions remain failed at the previously observed head. Railway still has only a production environment. Dedicated staging, actual demo/provider/payment/Telegram evidence, native devices, restore/rollback and soak acceptance remain open. No deployment or financial permission change is authorized by local PASS.

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

## Cross-chat intake checkpoint, 17 October 2026

ST1-SOURCES is still FAILED. Both full DOCX bodies and text exports match all
14,226 ledger rows; all 1,586 heading entries and 242 seeds were ingested.
Individual acceptance review remains incomplete, including repository child
clauses retained through the existing register. See source_coverage.json for
exact reconciled counts, not a claim that all rows are product features.

The first new diagnostic run recorded 70 passed / one database setup error
because the owned localhost test cluster was stopped. After restarting only
that cluster, the same checks recorded 71 passed with zero skips. Both are
modified-worktree diagnostics, not frozen-release acceptance. The clean a23e088f
local manifest failed its SDK gate because it was invoked with the runtime
interpreter; use the existing separate SDK venv for that group. Preserve the
failure and run the full exact-commit suite after freezing this source.

Missing blueprint_modules.csv and unsupplied chats are inaccessible-source
items. The many unfinished code/acceptance reviews remain local work, not external
blockers. Production, provider, broker-demo, isolated staging/soak, financial,
independent review and required hosted-check gates remain unclosed.

## Current continuation findings, 16 October 2026

Stage 1 remains FAILED. The 51d2f59e focused baseline passed 32 executed tests.
Repairs subsequently passed 71 diagnostic tests in a modified worktree, including
real SQL against a newly migrated owned localhost database. These diagnostics
are not frozen-commit acceptance; see the current evidence section.

Configuration overrides previously accepted duplicate aliases, Boolean schema
versions and malformed symbols. Environment-label precedence could mask production.
The DB query admitted metadata-only records. These defects are repaired locally;
strict scan reads now require recent analysis-readiness, matching classification,
provider candle/quote capabilities and non-delisted mappings. Fresh registry
timestamps do not prove candle freshness, entitlement, spread or liquidity.

Remaining local focused work: actual provider-bound qualification and refresh,
bounded retention/hysteresis, owner overrides and reasons, other signal and
learning paths, web/Telegram presentation, and independent new-order enforcement.
Do not label these gaps external or start the redesign phase while Stage 1 is open.

Fresh read-only control-plane evidence confirms only a production Railway
environment, API at 9865a3d1 and public web at f026bd16, and a crashed historical
soak observer. PR #201 remains draft with required independent last-push approval;
manifest/release-certification jobs still cannot start because of GitHub billing.
No protected check was bypassed. See evidence/continuation-20261016/.

Current Stage 1 acceptance: **FAILED — not complete**. Local integration,
foundation fixes and the complete 3,984-test suite now pass on c411ebbb. Remaining
source-specific acceptance review is local work, not an external blocker.
Independent review and hosted checks remain external gates. This ledger does
not declare Stage 1 complete or begin the next stage.

| ID | Status | Owner/component | Evidence / next action |
| --- | --- | --- | --- |
| ST1-TEST | VERIFIED | Engineering / local verification | Clean unchanged c411ebbb: 3,984 passed, zero failed/errors/skipped; all 32 orchestration steps pass. Both local browser modes and Android/iOS exports pass. See COMPLETION_EVIDENCE.md and retained receipts for scope. This verifies the local suite, not product-wide acceptance. |
| ST1-FOCUSED-UNIVERSE | FAILED | Stage 1 / focused-universe scanner | 10 core + up to 5 optional candidate contract is preserved. `configs/focused_universe.json`, `core/focused_universe.py` and `engine/core.py` now offer classification-checked, capped, no-fallback scan selection behind `FOCUSED_UNIVERSE_ENABLED=0` by default. Enabled behavior explicitly rejects non-staging environments. Tests were added but could not execute in hosted CI (zero job steps). Qualification scoring, independent broker/order-entry boundaries, other signal paths, web, Telegram, all market/provider certifications, local exact-head test execution and production rollout remain **unverified/not complete**. Existing positions and live permissions unchanged. |
| ST1-SOURCES | FAILED | Architecture and component owners | The inventory retains current and historical clauses, but many have no source-specific implementation/acceptance disposition. Resolve each applicable clause with code and meaningful tests; preserve superseded/optional context explicitly. See the generated matrix, not old PASS reports. |
| ST1-INTEGRATION | IMPLEMENTED | Repository maintainers | Blueprint ancestry, legal merge and recovered provider/ML fixes are committed, with browser attribution and fixture repairs. Complete the draft PR handoff; main still requires independent last-push approval and manifest/release-certification checks. |
| EXT-CI | BLOCKED_EXTERNAL | GitHub billing/account owner | `evidence/github-latest-annotations.json`: jobs never started because the account is locked due to a billing issue. Restore GitHub Actions availability and rerun required checks on the proposed SHA. |
| EXT-MOBILE-SECURITY | BLOCKED_EXTERNAL | Expo/node-forge maintainers and release owner | Locked npm audit returns four high rows from GHSA-86w9-cpqp-85rv; the official advisory lists no patched version. Await a trusted patch or separately review a supported replacement, then reinstall, audit, export and test devices. Do not suppress it or downgrade Expo to the audit's incompatible suggestion. |
| EXT-RUNTIME | BLOCKED_EXTERNAL | Deployment operator | GitHub deployment metadata and public GET are available; no authenticated current runtime/schema/configuration audit or promotion occurred. Capture exact deployment SHA/image/schema/configuration and staging evidence. |
| GAP-PUBLIC-ROUTES | FAILED | Deployment/frontend integration | October 15 public GET: `/` serves service JSON, `/login` is 404, `/app` serves retained HTML. The new public/account site is not proven to be serving this domain. Complete isolated cutover acceptance and a separately reviewed deployment; do not infer public-site readiness from `/healthz`. |
| EXT-PROVIDERS | BLOCKED_EXTERNAL | Data operations | Certify each enabled provider, market class, entitlement and timeframe in the actual environment, with source timestamps and outage evidence. Local mock certification is insufficient. |
| EXT-BROKERS | BLOCKED_EXTERNAL | Authorized broker/account operator | Supply dedicated demo accounts and scoped authority; run full per-adapter lifecycle/reconciliation tests. Live authorization is outside this task and remains unchanged. |
| EXT-JOURNEYS | BLOCKED_EXTERNAL | Product/operations | Dedicated staging Telegram, SMTP, APNs/FCM, mobile signing and test-mode billing evidence required. Device and external round trips are not replaced by TypeScript or source tests. |
| EXT-RECOVERY | BLOCKED_EXTERNAL | Infrastructure operator | Retain actual isolated backup restoration, RPO/RTO, alerting, restart reconciliation and sustained exact-SHA soak evidence. |
| EXT-POLICY | BLOCKED_EXTERNAL | Product/legal owner | Recovered policy text and consent controls require accountable content/jurisdiction review. No legal certification is claimed. |
| GAP-BROKERS | NOT_IMPLEMENTED | Broker adapters | Complete required execution adapters beyond the catalogue's ready mt4/mt5/bybit entries; connection-only/integration labels do not satisfy execution requirements. |
| GAP-RESEARCH | FAILED | Quant/research | Finish retained research/master clauses, including independent causal/out-of-sample/forward acceptance; current immutable storage safeguards alone do not prove statistical validity. |
| GAP-FULFILLMENT | FAILED | Billing/support/privacy | Demonstrate manual refund/privacy request completion and retention controls; ticket creation is only intake. |

The next local action is ST1-SOURCES: reconcile source-specific dispositions,
beginning with the 991 formal specification/master entries and 19 V7 mappings,
then resolve historical conflicts against those authorities. Their IDs, text,
hashes and known mappings are preserved in requirements.json. They are not 9,916
independent product features: source sections, historical versions and PR context
overlap. Associate each applicable clause with active code, explicit gaps and
scoped evidence; retain superseded/optional rationale. Do not rerun the passed
runtime suite merely to update documentation; check subsequent changes according
to their scope. Never weaken risk, calibration, ownership or evidence thresholds.

No production migration, configuration change, customer data write, billing
operation, broker order or real-money permission change is authorized by this
handoff. External blockers do not justify marking unrelated local work complete.


## Latest continuation (16 October 2026)

- Retry of GitHub Actions run `38932482649` generated attempt 2; jobs
  failed before executing any steps. Later run `38943080448` at
  `e908bfba959b3d35fdeccfae6af14221059b1fff` also reports failed
  manifest/release-certification jobs with zero steps. No successful hosted
  coverage or release approval can be inferred.
- A read-only fetch of the deployed hostname resolved `/` to `/app`, which
  displayed a session-restoration workstation. `/login` returned HTTP 404.
  This is evidence of the routing gap, not authenticated/browser E2E certification.
- Source-review work, exact-head Python/JS suites, externally provisioned
  broker-demo and staging Telegram tests, full Next public-site cutover,
  backup restoration and rolling/soak verification remain open. Do not merge
  draft PR #201 or deploy trading changes based on local/static review alone.


## Connected Railway runtime reconnaissance — 16 October 2026

Read-only connector inspection of Railway project `trading-bot-account2`
(production environment) found:

- API `SignalRankAI` and analytics worker deployed at
  `9865a3d1bcee632bfd9347e50d5de34d355225d9`, from
  `fix/provider-discovery-readiness-20260923`.
- `SignalRankAI-Public-Web` deployed at
  `f026bd16d90c0fbde2292e326525524fd75966ea`, from
  `fix/release-recovery-20261008`. The web and backend are not on
  one release SHA and neither runs the Stage 1 PR head.
- The connected project has one Railway environment, `production`, and
  no dedicated Railway staging environment. No staging soak for PR #201
  can be inferred.
- `signalrank-readonly-soak-20261012` is marked CRASHED. Its final
  read-only sample at 2026-10-16 05:14 UTC recorded 72 hours of
  process observations but explicitly returned
  `release_soak_certified=false`,
  `aggregate_database_observation_window_24h_passed=false` and
  `financial_readiness_certified=false`.
- The final sample reported no confirmed delivery within one hour,
  no signal generation within 24 hours, and no verified broker connection.
  It observed an MT5 credentials-saved record with `verified=0`,
  `execution_enabled=0`, and broker reconciliation status UNKNOWN.
  The sample included last confirmed delivery on 2026-10-06.
  This is a scoped observer report, not a query of every customer
  account or a claim that the trading engine is permanently broken.
- Read-only inspection found the production Postgres online with two
  warnings; verify their type before modifying storage.
- Attempts to start an isolated Vercel sandbox against the PR head
  were refused with 403 FORBIDDEN by the connected Vercel project.
  Thus a fresh full-stack end-to-end test was not run in that environment.

**Release impact:** The latest PR cannot be released/merged based on these
observations. First restore independent CI, provision staging resources,
run exact-SHA environment and broker-demo certification, resolve the
reported delivery/scan drought and reconcile deployment identities.
Do not restart/modify production trading workers as an unreviewed
test workaround.
