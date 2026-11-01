# Server operations handoff — 1 Nov 2026

Written by the server-side Claude session that migrated SignalRank and NATA off Railway and now operates
the production server. Read this before changing deployment, environment, data or ML behaviour, so the
desktop Claude Code session and the server session do not undo each other's work.

All figures below were read from production on 1 Nov 2026 (UTC) unless a date is given.

## 1. Where production runs now

- **Host:** one Contabo VPS (Ubuntu 24.04, 11 GiB RAM), public IP `157.173.99.72`. Railway application
  services are stopped; Railway's SignalRank Postgres/PgBouncer/Redis are still running only as a stale
  fallback (no writes since the 29 Oct cutover).
- **Containers (Docker Compose project `signalrank`):** `bot`, `worker`, `engine`, `analytics` (one backend
  image built from this branch), `web` (Next.js from `frontend/`), `postgres:18`, `redis-a`, `redis-b`,
  `caddy`.
- **Public names (Caddy, automatic HTTPS):**
  - `www.signalrank.criloxsolutions.com` and `signalrank.criloxsolutions.com` → Next.js website; the paths
    `/telegram*`, `/webhook*`, `/webhooks/*`, `/paystack/*`, `/healthz`, `/readyz`, `/livez` go straight to
    the bot.
  - Telegram webhook: `https://www.signalrank.criloxsolutions.com/telegram/webhook`.
  - `157-173-99-72.sslip.io` → bot (the website's `SIGNALRANK_PLATFORM_API_ORIGIN`);
    `web.157-173-99-72.sslip.io` → website.
  - Caddy sets `X-Real-IP` from the real client and trusts forwarded addresses only from the Docker
    network; `SIGNALRANK_CLIENT_IP_SECRET` is shared by the website and the backend.
- **NATA** runs on the same server (Compose project `nata`), live at `https://api.natalagoscouncil.com.ng`
  since 1 Nov.

## 2. How code reaches production

- **Auto-deploy follows this branch** (`feat/frontend-rebuild-and-stage1-hardening`), checked every
  3 minutes.
  - **Backend:** a new commit is built, a database backup is taken, `scripts/controlled_migrate.py`
    runs, and the bot is health-checked. It rolls back automatically if the new version is unhealthy and
    the schema did not change.
  - **Website:** it is rebuilt only when `frontend/` or `Dockerfile.frontend` changed.
  - **Commits that change nothing that runs** (`docs/`, `requirements/`, `tests/`, `frontend/` for the
    backend, `*.md`…) are skipped, so governance-only commits do not restart production.
  - **A commit whose deploy failed is not retried**; the next commit is.
- **Build notes:** the server builds the backend from a simplified copy of `Dockerfile`, using the same
  builder steps without the minimal-runtime stage. **If you change the builder stage or the requirement
  files list in `Dockerfile`, mention it in a commit message.** The tooling copies `Dockerfile`'s builder
  stage but should be checked.
- **Release identity:** each deploy sets `RAILWAY_GIT_COMMIT_SHA`, `EXPECTED_RELEASE_COMMIT` and
  `EXPECTED_RELEASE_BRANCH` to the deployed commit, so `assert_release_source.py` and
  `controlled_migrate.py` pass for exactly that commit.

## 3. Production settings changed on the server today

These are server-side overrides (`sr env-set`, stored in `/opt/signalrank/env/overrides.json`); they are
**not** in Railway and not in this repository.

| Setting | Value | Services | Why |
|---|---|---|---|
| `EXPECTANCY_HARD_BLOCK_ENABLED` | `0` | backend | Was `1`: with no delivered outcomes every candidate is refused and evidence can never form (documented in `engine/expectancy_shadow.py`). No signal had been issued since **2026-10-11 10:49 UTC**. `0` is the code default. |
| `EMAIL_DELIVERY_ENABLED` | `1` | worker | Was `0` in the worker, the only role that runs `_email_delivery_loop`, so no email was ever sent. SMTP login to `smtp.go54mail.com:587` was verified. One stale `magic_login` from 11 Oct was marked `failed`, not sent. |
| `ML_ALLOW_ADAPTIVE_THRESHOLD_AROUND_CERTIFIED`, `ML_ADAPTIVE_THRESHOLD_MAX_DELTA`, `ML_PROB_THRESHOLD` | `1`, `0.14`, `0.70` | engine | Owner asked for a 0.70 ML pass mark. Effective raw threshold is now 0.70 (it was the artifact's certified 0.84). |
| `CRYPTO_PAIRS`, `FX_PAIRS`, `STOCK_TICKERS`, `INDEX_TICKERS`, `COMMODITY_TICKERS`, `TRADABLE_ASSETS`, `ASSET_DISCOVERY_MODE=manual`, `DYNAMIC_UNIVERSE_ENABLED=0` | see below | backend | Owner wants a fixed universe of the top 10 + 5 extra per class. The database registry universe was mostly stablecoins and illiquid tokens with no candles. |

Universe now pinned (`TRADABLE_ASSETS`):

- **Crypto:** BTC, ETH, XRP, BNB, SOL, DOGE, TRX, ADA, LINK, AVAX, TON, SUI, DOT, LTC, BCH (USDT pairs).
- **Forex:** EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD, EURJPY, GBPJPY, EURGBP, AUDJPY,
  EURCHF, EURCAD, CADJPY, CHFJPY.
- **Stocks:** NVDA, MSFT, AAPL, AMZN, GOOGL, META, AVGO, TSLA, JPM, LLY, V, NFLX, AMD, ORCL, WMT.
- **Indices** (only 10 are mapped in `services/asset_mapper.py`): US500, NAS100, US30, GER40, UK100, JP225,
  FRA40, EU50, AUS200, HK50.
- **Commodities** (only 4 are mapped): XAUUSD, XAGUSD, WTI, BRENT.

## 4. Findings from production (evidence)

1. **No signals since 11 Oct.** Last 24 h of `decision_log`: `risk/expectancy_unavailable` 120,747,
   `no_usable_candles` 95,934, `risk/volatility` 17,577, many `validation:SL too wide … (max 8.0% for crypto)`.
   No `signal_deliveries` in 21 days.
2. **Expectancy shadow evidence never matures:** 93,297 `decision_log` rows with `meta.layer='expectancy'`
   since 30 Oct, **0** with `shadow_r`. The shadow outcome follow-up is not running for these rows, so
   `EXPECTANCY_SHADOW_BOOTSTRAP_ENABLED` could never open the gate either.
3. **ML model inverted for current markets.**
   - The serving model was trained 29 Sep and certifies a raw threshold of 0.84.
   - Stablecoin-like assets (USDS, PYUSD, RLUSD, PAXG, XAUT) score 0.87–0.91. Real coins score
     0.05–0.64 raw (e.g. BCH 0.58, ETC 0.64, DOGE 0.11, NEAR 0.06).
   - Starvation recovery declines everything (`score_below_recovery_floor`,
     `raw_probability_below_recovery_floor`).
   - At 0.70, real coins still rarely pass; retraining is required.
4. **ADX sometimes invalid** → `Weak trend (ADX 10) | Low directional efficiency (0.00) | Tight range`
   rejections on assets that are trending.
5. **Degenerate levels:** `validation:LONG: Entry (3876.1) must be above SL (3876.1)` (also 283.53): a
   strategy emits SL equal to entry.
6. **External credentials:**
   - OpenAI startup probe returns HTTP 401 (key rejected), so AI features fall back to local.
   - MetaAPI probe reports `provider_unavailable`; the owner will replace the key.
7. **Database pressure in analytics:**
   - `[db_admission_timeout] label=adaptive.monitor` with capacity 2.
   - `[continuous_improvement] scheduled review failed` ends in asyncpg `TimeoutError`.
   - Postgres cancels parallel scans on `ml_rejected_signals`. That table grows by 50k–110k rows/day
     because of the stablecoin universe; it should slow down now that the universe is fixed.
8. **Users:** 12 (8 free, 4 owner). All have `execution_mode=manual`, one broker connection has saved
   credentials, 6 paper accounts. `GLOBAL_EXECUTION_KILL_SWITCH=1`.

## 5. Owner requests (1 Nov 2026), verbatim in substance

- ML pass mark 0.70 (done, §3).
- Retrain the model on all past data, and learn from every rejected candidate and every candidate that
  fails any phase, including stablecoin exclusion.
- Keep improving accuracy, outcome tracking and OHLC fetching continuously; a recurring review by Claude.
- Live auto-trading available so users can opt in. **Server session position:** build and test the opt-in
  path on paper and demo accounts first. Real-money enablement only after the retrained model shows
  positive forward results. AGENTS.md also forbids enabling real-money trading as part of recovery.
- Owner replaces the MetaAPI key (account linking and broker real-time prices).
- Improve strategy creation and backtesting, and everything else in the ecosystem.
- Five asset classes, top 10 + 5 extra each, real-time data where available. Five more indices and eleven
  more commodities need mapper/provider entries.

## 6. Split of work (proposal — edit this table if you take something)

| Area | Taken by |
|---|---|
| Server, deploys, environment, data copy, monitoring relay | server session |
| Fix shadow outcome tracking for expectancy and ML-rejected rows | server session |
| Exclude stablecoins and pegged tokens in discovery and in training data | server session |
| ADX validity bug and `entry == stop` level bug | server session |
| Asset mapper: 5 more indices and 11 more commodities with provider symbols | server session |
| Retraining pipeline that learns from rejected and shadow outcomes (champion/challenger, no auto-promotion without evidence) | server session, review by desktop |
| Strategy builder, backtesting UX, frontend, Telegram UX | desktop session |

Both sessions commit to this branch. Pull and rebase before every push, keep commits small, and follow
`AGENTS.md` (tests, governance regeneration, release documents).

## 7. Later on 1 Nov (evening)

- **Asset discovery is back on `ASSET_DISCOVERY_MODE=auto`**, with `CRYPTO_TRENDING_TOP_N`, `CRYPTO_UNIVERSE_TOP_N`,
  `STOCK_TRENDING_TOP_N` and `INDEX_TRENDING_TOP_N` set to `15`.
  - `manual` made `/readyz` report `provider_coverage.ok=false`, because manual symbols are not provider-backed.
    The deploy health check then failed and rolled back `cc1ffc8`; it was redeployed after the fix.
  - Pinned `TRADABLE_ASSETS` and `DYNAMIC_UNIVERSE_ENABLED=0` remain.
- **1-minute timeframes removed** (`*_TIMEFRAMES=5m,15m,1h,4h,24h`).
  - 1m signals expired before dispatch (`opportunity_decayed ... max=2.0m`), so users received few of them.
  - The ones they did receive often ended as `missed_entry`, because entry was not touched before the very short
    expiry ("entry not triggered" messages).
- **Owner replaced the MetaAPI key:** `metaapi_startup_probe status=PASS`. The OpenAI key is still rejected (401);
  the owner is replacing it.
- **Retraining, found while running `python -m ml.train_model` on the server:**
  - The 90-day shadow-rejected load fails at `DB_COMMAND_TIMEOUT=45` s. `ml_rejected_signals` is a **view** over
    `decision_log` (2.6 GB, 1.9 M rows).
  - Without those rows the dataset is 60–392 rows, below `ML_MIN_TRAIN_ROWS` (667), so training is skipped.
  - A one-off run with longer timeouts was started; the result will be recorded here.
- **`[store_signal] failed … SignalDedupBlocked min_interval`** was logged at ERROR for normal duplicate
  suppression; it is now logged at INFO (`db/pg_compat.py`).
- **Daily review:** a scheduled cloud session reviews production every day at 06:37 Lagos time and writes
  `reports/YYYY-MM-DD.md` on the `reports` branch of the private ops repo.

## 8. 2 Nov 2026 (night): learning from every outcome

- **Retrain with all rejected evidence** (`ML_MAX_SHADOW_REJECTED_EFFECTIVE_RATIO=50`, 45-day lookback, long DB
  timeouts) trained on 231,747 rows and was **rejected by the quality gate**: accuracy 0.69 vs majority
  baseline 0.82, AUC 0.62, expected R −0.17 on the validation slice. The 29 Sep model stays in service. The
  rejected-setup population is dominated by losers (SL 139k vs TP 42k), and the current features cannot yet
  separate the winners. More delivered outcomes and the per-asset scorecard below are the next levers.
- **Expectancy shadow tracking now runs in analytics** (`runtime/analytics.py`). It was registered only in the
  worker, where `SHADOW_OUTCOME_TRACKER_ENABLED=0`, so expectancy-layer rows were never followed forward.
- **Per-asset strategy scorecard** (`services/strategy_scorecard.py`):
  - analytics rebuilds it every 3 h from issued outcomes (weight 3) plus every shadow-tracked rejected setup;
  - cells per asset × timeframe × strategy × direction, with fallback to asset, asset class × timeframe, and
    asset class;
  - the engine multiplies the score by at most 0.85–1.15, and only when the cell's Wilson 95 % win-rate
    interval is clearly above or below the cell's own break-even win rate (≥ 40 outcomes);
  - `STRATEGY_SCORECARD_MODE=off|shadow|apply` (code default `shadow`: annotate `sig["strategy_scorecard"]`
    only). It never creates a signal or bypasses a gate.
