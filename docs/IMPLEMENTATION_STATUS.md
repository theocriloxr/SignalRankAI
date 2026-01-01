# SignalRankAI — Implementation Status (Spec → Code)

This matrix maps the functional spec to current code paths and highlights remaining gaps.

## Access control
- User registration (/start)
  - Implemented (SQLite): `db/database.py::record_user_seen` + `/start` in `signalrank_telegram/commands.py`
  - Implemented (Postgres best-effort): `/start` upserts `db.models.User` when `DATABASE_URL` is set
- Tier detection
  - Telegram bot (SQLite): `signalrank_telegram/access.py::resolve_user_tier`
  - Web/API (Postgres): `db/access.py::resolve_user_tier`
- Owner bypass
  - Owner IDs: env `OWNER_TELEGRAM_ID`/`OWNER_IDS`
  - Temp bypass: Redis state + owner commands (`signalrank_telegram/owner_commands.py`)

## Data ingestion
- Crypto (Binance WS + REST fallback): `data/binance_ws.py`, `data/fetcher.py`
- FX feed: uses AlphaVantage candles when `ALPHAVANTAGE_API_KEY` is configured (`data/fetcher.py`). If not configured, FX candles are disabled (returns empty) rather than generating synthetic OHLC.
- Normalization: `data/indicators.py` + engine normalization in `engine/signal_controller.py`

### Real-feed configuration (no demo fallbacks)
- `TRADABLE_ASSETS` (comma-separated) — used only if pair discovery returns no assets.
- `FX_PAIRS` (comma-separated) — optional list of FX symbols (e.g., `EURUSD,GBPUSD`). No hardcoded FX pairs.
- `ALPHAVANTAGE_API_KEY` — required to fetch FX candles.

## Strategy engine
- Strategy modules: `strategies/` (trend/momentum/volatility/structure)
- Regime detection: `engine/regime.py`

## Consensus/filtering
- Consensus + filtering: `engine/consensus.py`, `engine/ranking.py`, `engine/scoring.py`
- HTF alignment + correlation filtering: partially implemented in engine pipeline (verify thresholds/coverage)

## Scoring/risk
- Scoring: `engine/scoring.py`
- Risk: `engine/risk.py`

## Dispatch/notifications
- Tiered dispatch formatting: `signalrank_telegram/formatter.py` + dispatch logic in `signalrank_telegram/bot.py`
- Alerts prefs storage (SQLite): `db/database.py::{get_alert_prefs,set_alert_prefs}`
- Rate limiting + kill switch: `core/redis_state.py`

## Outcomes & trust engine
- Outcome tracking hooks exist (notifications in `signalrank_telegram/bot.py`), but full real-time monitoring pipeline may still need tightening for all TP levels.

## Performance/reporting
- Performance snapshot: `/performance` in `signalrank_telegram/commands.py`
- Scheduled recap: weekly recap scheduler in `signalrank_telegram/bot.py`

## Monetization/payments
- Paystack webhook + signature verification: `web/app.py`
- Postgres subscription activation/renewal: `db/repository.py`
- VIP seat cap enforced: web + legacy SQLite path
- Referral system (3 invites → 7 days Premium): implemented in SQLite (`db/database.py`) and `/start` processing.

## Security/reliability
- Kill switch: Redis-backed flag checked before dispatch
- Rate limiting: Redis counters for commands
- Logging: audit logger hooks added for referral processing

## ML extension
- Data model supports outcomes + signals; feature snapshot capture is a future enhancement.
