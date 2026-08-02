# SignalRankAI v1.3.6.5 — Production Integrity, Profile Routing and Dynamic Discovery

Release date: 2026-08-02
Release fingerprint: `v1.3.6.5-production-integrity-hardening-20260802`
Database migration head: `0034_production_integrity`

## Release purpose

This release repairs the failures demonstrated by the August 2 staging transcripts and makes the codebase capable of progressing through a controlled live-trading certification process.

It deliberately remains fail-closed. Source hardening does not prove profitability, authorize unrestricted live money, guarantee a 60% win rate, or turn an uncalibrated model score into a probability.

## Operational scorecard addressed

| Area | v1.3.6.5 implementation |
|---|---|
| Telegram delivery and callbacks | Existing webhook/Redis-stream flow preserved |
| Signal freshness | Rechecked at delivery and at actual paper/copy/live execution time |
| Signal deduplication | Cross-timeframe thesis fingerprint, database transaction lock and per-user asset cooldown |
| Signal score calibration | Held-out calibration evidence persisted; uncalibrated values hidden from public probability labels |
| Signal quality | Geometry, risk/reward, freshness, provenance, profile and calibration quality gates |
| Entry-trigger detection | Preserved and tied to immutable delivered plans |
| TP/SL detection | Trusted quotes plus bounded candle-extrema recovery with conservative same-candle ordering |
| Outcome ordering | Monotonic stage ranks; terminal outcomes suppress delayed lower-stage notifications |
| Outcome completeness | Worker continuously projects proof-backed deliveries into canonical outcomes |
| Performance reporting | Worker continuously reconciles performance ledgers; public output fails closed until certified |
| Paper trading | Freshness, one-position-per-asset, profile, deviation and concentration controls |
| Paper risk | Per-position notional, total exposure, aggregate open risk and daily realized-loss circuit breakers |
| Shadow learning | Rejected-signal tracking and health/certification gates |
| Engine Pulse | Reconciled current-cycle and confirmed-delivery health state |
| Provider coverage | Online provider discovery with provenance and production fail-closed coverage checks |
| User profiles | Aggregate profile demand shapes scans; the same policy is enforced through delivery and execution |
| Live/copy trading | Technically gated and disabled until all runtime certifications pass |

## 1. Signal and delivery deduplication

A canonical thesis fingerprint uses normalized asset, direction, strategy family and a configurable logarithmic entry-price band. Timeframe is excluded by default, so the same BTC or SOL thesis cannot evade deduplication merely by being regenerated on another timeframe or with a tiny repricing.

The primary persistence path now:

- acquires a PostgreSQL transaction advisory lock per thesis;
- checks the recent canonical thesis window before inserting;
- prevents concurrent engine replicas from creating the same setup;
- persists thesis and provider provenance;
- preserves the delivered plan after confirmation.

Distribution additionally uses a database-backed per-user/per-asset lock and the default four-hour cooldown. Reserved, sending and confirmed rows participate in race protection. Owner/admin accounts no longer bypass the cooldown unless a deliberate non-production diagnostic bypass is enabled.

## 2. Dynamic provider-backed asset discovery

The engine is not restricted to a hardcoded symbol list. It can discover and refresh tradable instruments from configured providers, including crypto exchanges, MetaApi broker symbols and supported equity/provider catalogues.

Discovered assets are:

- normalized into canonical symbols and asset classes;
- checked for provider capability and active/trading status;
- ranked using liquidity/volume and provider support where available;
- checked for usable history and fresh market data before signal admission;
- tagged with discovery/provider provenance;
- rejected from production live/copy execution when only an untrusted static fallback is available.

Manual allowlists remain useful as an operator restriction, but static fallback is disabled by default. A production deployment must prove provider discovery and coverage rather than silently falling back to a small hardcoded universe.

## 3. Profile-aware generation, ranking and distribution

SignalRankAI retains one efficient shared provider scan rather than downloading the same market data separately for every user. Active user profiles are aggregated into a profile-demand snapshot that prioritizes relevant asset classes, preferred assets and timeframes in the discovered universe.

Each candidate is then personalized and re-authorized per user using the canonical merged profile:

- scalp/day/swing/position style;
- asset classes;
- preferred and blocked assets;
- timeframes;
- strategies;
- market sessions;
- minimum score/quality requirements;
- risk profile and risk per trade;
- daily trade/loss and position limits;
- notification preferences;
- manual, paper, copy or live execution mode;
- subscription and execution entitlement.

The same policy is enforced at Telegram delivery, resend/recovery, opportunity ranking, paper trading, MT5 and Bybit execution. A fallback path may not bypass profile authorization.

## 4. Honest score and probability presentation

Raw strategy/ML scores are no longer assumed to be probabilities. Training calibration is evaluated out-of-sample and calibration evidence is stored with the model artifact.

Public probability display requires:

- a validated calibration method/version;
- a sufficient held-out validation sample;
- acceptable configured Brier score and expected calibration error;
- persisted calibrated probability and evidence metadata.

When those conditions are absent, the bot shows a score/confidence label rather than a false `95%` or `100%` probability claim.

## 5. Signal quality gate

Before a candidate can be delivered or executed, the quality gate checks:

- valid long/short entry, stop and target geometry;
- finite prices and sensible target ordering;
- configured minimum final risk/reward;
- score/confluence requirements;
- generated-at freshness;
- asset/provider provenance;
- calibrated ML evidence when required;
- user-profile compatibility;
- thesis and exposure conflicts.

Quality rejection remains observable and eligible for shadow evaluation rather than disappearing silently.

## 6. Paper-trading integrity

Paper admission is rechecked when the position is actually opened. A signal that was fresh when queued cannot open hours later.

Default maximum ages:

- 5m: 5 minutes
- 15m: 10 minutes
- 1h: 30 minutes
- 4h: 90 minutes
- 1d: 6 hours

Portfolio controls include:

- one open position per asset unless separately certified pyramiding is introduced;
- maximum positions per asset class;
- maximum notional per position;
- maximum total exposure;
- maximum aggregate open risk;
- daily realized-loss circuit breaker;
- maximum entry deviation, spread, slippage and fees;
- user-profile risk and trading-mode enforcement;
- canonical delivery evidence before opening;
- `/paper_close_all CONFIRM` before reset;
- reset remains blocked while positions are open.

## 7. Outcome truth and notification ordering

The outcome tracker combines trusted live quotes with a bounded micro-candle high/low check to recover TP or SL touches that occurred between polling cycles. It avoids using candle movement from before the signal existed and applies a conservative policy when TP and SL are both possible within the same candle.

Outcome stages are monotonic. TP3/SL/expired/cancelled terminal states prevent delayed TP1 or TP2 notifications from being delivered afterward. Exact observed target/stop levels and provenance are persisted.

The worker continuously:

1. creates missing canonical outcome projections for proof-backed deliveries;
2. reconciles lifecycle state;
3. rebuilds user performance ledgers;
4. updates health used by `/readyz` and release gates.

## 8. Performance truth and public claims

Performance is grouped by independent thesis so repeated repricing or cross-timeframe duplicates from one market move are not treated as independent predictions.

Ordinary users do not receive provisional win-rate, return or R-multiple numbers while the ledger is uncertified. Owner/admin accounts retain a clearly labelled diagnostic view for repair and audit.

A public 60% claim is permitted only when all configured evidence gates pass. Defaults require:

- at least 200 terminal independent samples;
- at least 100 unique theses;
- at least 95% terminal coverage;
- observed independent-thesis win rate of at least 60%;
- the 95% Wilson lower confidence bound also at or above 60%;
- verified performance-ledger reconciliation;
- a dedicated performance-claim certification ID.

The code cannot guarantee that market results will satisfy this gate.

## 9. Shadow tracking and Engine Pulse

Rejected setups remain eligible for post-signal shadow tracking. Shadow results use candles after the candidate timestamp and expose health/heartbeat state.

Engine Pulse now separates current-cycle progress from cumulative historical accounting and records a reconciled health snapshot. Production release gates require explicit certification for both shadow tracking and Engine Pulse integrity.

## 10. Live auto-trading and copy trading

Real execution remains off by default. Activation requires all safety dependencies, including:

- production environment and testing disabled;
- exact owner/user, broker-account, provider and symbol allowlists;
- demo certification;
- production-integrity and live-runtime certification IDs;
- calibrated model artifact;
- freshness, profile routing, paper, delivery, Telegram, outcome, performance, shadow, pulse, OHLC, test and secret-scan evidence;
- provider-backed discovery with static fallback disabled;
- maximum position, daily loss and total exposure values;
- encryption and provider credentials;
- bounded activation window;
- global kill switch cleared deliberately;
- broker-specific protections and reconciliation.

Copy trading additionally requires a separate copy-trading certification ID.

## Migration

Migration `0034_production_integrity` adds the required thesis, calibration, outcome-stage and paper-position integrity fields/indexes. It must be applied before the new code is considered ready.

## Source validation completed

- Production-focused regression matrix: 144 passed.
- Dependency-independent broad matrix: 405 passed, 1 skipped.
- v1.3.6.5 integrity verifier: passed.
- Schema audit: passed, 34 revisions, head `0034_production_integrity`.
- Python compilation: 818 files, zero errors.
- Generated governance registry check: passed.

The validation container does not provide `python-telegram-bot` or APScheduler, so the complete repository suite could not be collected there. Those packages are declared project runtime dependencies and must be tested in the user’s local virtual environment and Railway deployments.

## Certification boundary

This release is source-certified for staging deployment. It is not automatically certified for unrestricted live trading, copy trading, paid public launch or a 60% marketing claim. Those states require real post-deployment evidence and the release/financial guards are designed to remain blocked until that evidence exists.
