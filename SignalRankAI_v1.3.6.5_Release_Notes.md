# SignalRankAI v1.3.6.5 — Production Integrity Hardening

Release date: 2026-08-02  
Release fingerprint: `v1.3.6.5-production-integrity-hardening-20260802`

## Purpose

This release repairs the operational failures observed in the August 2 staging transcripts and makes the system capable of being certified for live auto-trading, copy trading, paid launch, and public performance reporting. It deliberately remains fail-closed until runtime and statistical evidence satisfies the release gates.

It does not promise a 60% win rate and it does not relabel an uncalibrated model score as a probability.

## Fixed operational scorecard

| Area | v1.3.6.5 source status |
|---|---|
| Telegram delivery and callbacks | Preserved and regression-covered |
| Signal freshness | Enforced at delivery and again at actual paper/copy/live execution |
| Signal deduplication | Canonical cross-timeframe thesis lock plus per-user asset lock |
| Signal score calibration | Raw scores visibly marked uncalibrated; probability display requires held-out evidence |
| Signal quality | Persisted quality gate, geometry, R:R, freshness, provenance and calibration checks |
| Entry-trigger detection | Preserved |
| TP/SL detection | Monotonic outcome stages and projection reconciliation added |
| Outcome notification ordering | Terminal and higher-stage events cannot regress to older stages |
| Outcome completeness | Proof-backed delivery projection and coverage readiness added |
| Performance reporting | Independent-thesis statistics and public-claim evidence gate added |
| Paper trading | Freshness, duplicate-asset, deviation, exposure and profile controls added |
| Paper risk control | Per-position, total exposure, asset-class concentration and close-all recovery added |
| Shadow learning | Post-signal candle filtering and truthful counters added |
| Engine Pulse | Uses current-cycle and confirmed-delivery truth instead of misleading mixed counters |
| Multi-asset/provider coverage | Online provider discovery, provenance and production readiness gates added |
| Profile personalization | One discovered universe, personalized eligibility/ranking/risk/execution per user |
| Production readiness | Source-certified for staging; live activation requires runtime certifications |

## Signal deduplication

The canonical thesis fingerprint combines normalized asset, direction, strategy family and logarithmic entry-price band. Timeframe is excluded by default so a repriced 15-minute and one-hour message representing the same trade thesis cannot bypass deduplication.

The primary database persistence path now:

- acquires a PostgreSQL transaction advisory lock per thesis;
- searches the canonical thesis window before insert;
- preserves entry, stop and targets after confirmed delivery;
- stores the thesis fingerprint and source provenance;
- refuses concurrent duplicate creation across engine replicas.

Delivery additionally acquires a per-user, per-asset transaction lock. Reserved, sending and confirmed delivery rows count as active exposure, preventing a live-delivery and resend race from sending two same-asset signals to one user. The default cooldown is four hours and owner/admin bypass is disabled by default.

## Dynamic online asset discovery

The engine is no longer confined to a hardcoded asset list. It discovers supported instruments from configured providers, including:

- Bybit instruments and liquidity;
- OKX instruments and tickers;
- Coinbase public products and statistics;
- CryptoCompare/Binance crypto markets;
- MetaApi broker symbols;
- Polygon stock instruments;
- configured FX and commodity providers.

Symbols are normalized, capability-checked and ranked by provider support, market history, freshness and liquidity. Manual asset lists supplement discovery by default. Hardcoded/manual-only operation occurs only when `ASSET_DISCOVERY_MODE=manual`, `fixed`, or `allowlist` is explicitly configured. Static fallback remains disabled by default.

Every signal persists asset-discovery provenance. Live and copy execution require trusted provider discovery unless explicitly certified otherwise.

## Profile-aware generation and distribution

SignalRankAI does not perform a full provider scan separately for every user. It builds one provider-discovered, quality-controlled market universe and uses aggregate active-profile demand to prioritize assets and timeframes.

Each user then receives a personalized opportunity plan based on the canonical database profile:

- scalp, day, swing or position style;
- allowed timeframes and asset classes;
- preferred and blocked assets;
- preferred strategies;
- market sessions;
- minimum quality threshold;
- risk profile and per-signal risk;
- maximum positions, daily limits and daily loss;
- notification style;
- manual, paper, copy or live execution mode;
- tier and execution entitlements.

The same profile is enforced by Telegram distribution, paper trading, copy trading and live execution. Legacy notification settings are consolidated into this authoritative profile path.

## Paper trading integrity

Paper signals are revalidated at actual fill time. A signal that was fresh when delivered but remained queued cannot open hours later.

Default maximum ages:

- 5m: 5 minutes
- 15m: 10 minutes
- 1h: 30 minutes
- 4h: 90 minutes
- 1d: 6 hours

Other controls:

- one open paper position per asset unless explicit pyramiding is certified;
- maximum two positions per asset class;
- maximum 20% notional per position;
- maximum 80% total account exposure;
- maximum 25 bps entry deviation;
- profile-aware direction, asset-class, timeframe, risk and position limits;
- `/paper_close_all CONFIRM` closes positions using current quotes before reset;
- `/paper_reset <balance> CONFIRM` remains blocked while positions are open.

## Outcome and performance truth

Outcome stages are monotonic. A TP3 result cannot later emit a delayed TP1 or TP2 as though it were new. Notification claims remain durable and idempotent.

Readiness now measures proof-backed delivery projection coverage. Production requires the configured minimum before performance truth can pass.

Performance reporting groups repriced/cross-timeframe duplicates into independent theses. A public 60% claim requires, by default:

- at least 200 terminal independent samples;
- at least 100 unique theses;
- at least 95% terminal coverage;
- observed win rate at or above 60%;
- 95% Wilson lower confidence bound at or above 60%;
- a separate performance-claim certification ID.

Until all requirements pass, `/performance` identifies the claim as not eligible.

## Calibration truth

Raw model output is displayed as `Model Score (uncalibrated)` unless all held-out calibration evidence exists:

- validation row count at least 100;
- persisted calibration version and artifact;
- validation flag true;
- Brier score no worse than 0.25;
- expected calibration error no worse than 0.10.

Only then may the user-facing card say `Calibrated win probability`. Live execution can require the same evidence.

## Live and copy-trading gates

Live and copy execution remain disabled until all relevant evidence IDs and safety controls are present. The release requires, among other checks:

- exact approved release commit;
- production-integrity certification;
- live runtime certification;
- calibration artifact certification;
- provider-discovery certification;
- freshness and profile-routing certification;
- paper-trading certification;
- outcome-tracker and performance-truth certification;
- copy-trading certification where applicable;
- exact owner/account/provider/symbol allowlists;
- exposure and daily-loss limits;
- broker reconciliation;
- global kill switch clear only during an approved activation window.

## Migration

Alembic head: `0034_production_integrity`

The migration adds production-integrity fields and indexes, backfills fingerprints safely, and enables `pgcrypto` before digest use.

## Validation performed

- integrated relevant suite: 114 passed, 1 intentionally deselected;
- v1.3.6.5 focused suite: 41 passed after UTC cleanup;
- all Python modules compile;
- Alembic reports one head: `0034_production_integrity`;
- production-integrity verifier: PASS;
- Railway decomposition verifier: PASS;
- production-cutover verifier: PASS.

The one deselected test imports an optional Telegram surface unavailable in the offline validation container. Railway already carries the declared runtime dependencies; runtime certification must still confirm them after deployment.
