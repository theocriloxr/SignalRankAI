# SignalRankAI Adaptive Strategy Intelligence — Architecture and Gap Analysis v1.1.0

## Executive assessment

SignalRankAI already had a mature deterministic signal pipeline, multi-provider OHLC ingestion, strategy groups, scoring, ML/Gemini/news/risk gates, persistence, Telegram delivery, delivery proof, shadow/outcome tracking, backtest helpers, walk-forward helpers, Redis coordination, PostgreSQL migrations, and Railway worker orchestration. The missing capability was a cohesive, runtime-connected, asset-specific learning layer that preserved evidence lineage and promotion governance.

v1.1.0 adds that layer without replacing the existing engine. Adaptive logic produces structured evidence and bounded profile recommendations. Research and shadow profiles cannot modify live scores. Only CANARY, LIMITED_LIVE, or APPROVED current profiles loaded through the profile registry can apply bounded weights, and all existing deterministic risk, news, deduplication, eligibility, delivery, and execution controls remain authoritative.

## Verified current signal path

```text
Provider OHLC
→ existing normalisation and timeframe plan
→ existing strategy groups
→ adaptive candle snapshot enqueue
→ adaptive data-quality validation
→ modular adaptive evidence components
→ approved-profile bounded weighting
→ existing score calculation
→ existing regime, microstructure, ML, Gemini, news and risk gates
→ existing deduplication and user eligibility
→ PostgreSQL signal persistence
→ adaptive evidence and sequence-reference persistence in the same short transaction
→ Redis/Telegram delivery
→ Telegram-confirmed delivery proof
→ outcome tracking
→ versioned dataset construction
→ chronological purged walk-forward evaluation
→ SHADOW challenger creation
→ owner-governed staged promotion
→ confirmed-live drift monitoring
→ suspension and rollback
```

## Components reused

- `strategies.run_all_strategies` remains the canonical strategy entry point.
- `engine.core` remains the scoring, filtering and signal-lifecycle authority.
- Existing data fetchers and provider failover remain authoritative for market data.
- Existing `market_candles` remains the canonical candle store.
- Existing `signals`, `outcomes`, `signal_deliveries`, and `trades` remain the truth sources.
- Existing Redis state remains the approved-profile distribution layer.
- Existing worker supervision remains the background-task owner.
- Existing risk, portfolio, tier, cooldown, and execution controls remain authoritative.

## New modules

- `engine/adaptive/types.py`: typed evidence, context, quality and profile contracts.
- `engine/adaptive/data_quality.py`: stale, duplicate, gap, impossible-OHLC and missing-data validation.
- `engine/adaptive/components/*`: separate ICT/SMC, price-action, supply/demand, Fibonacci, harmonic, Elliott, genuine-order-flow, Wyckoff and indicator components.
- `engine/adaptive/runtime.py`: evidence evaluation, profile resolution and bounded annotation.
- `engine/adaptive/candle_store.py`: bounded asynchronous canonical candle persistence.
- `engine/adaptive/sequence.py`: sequence hashes and summaries without candle duplication.
- `engine/adaptive/dataset.py`: deterministic chronological dataset manifests and evidence-category separation.
- `engine/adaptive/walk_forward.py`: purged chronological walk-forward validation with cost modelling.
- `engine/adaptive/learning.py`: distributed-lock analytics worker, candidate deduplication, WFO registration and drift suspension.
- `engine/adaptive/promotion.py`: staged promotion gate.
- `engine/adaptive/repository.py`: evidence persistence and approved-profile publication.
- `signalrank_telegram/adaptive_commands.py`: owner status, pause, resume, promote, suspend and rollback controls.

## Data and leakage controls

- Decision rows are sorted by decision timestamp and signal ID.
- No random train/test split is used.
- Every WFO fold derives family and regime weights only from its purged training window.
- Validation rows are later than the final training row.
- Future rows cannot affect earlier fold weights.
- Sequence references identify exact pre-signal candle sets through stable hashes.
- Full candle arrays are stored once in the canonical candle table and are not copied into signal rows.
- Backtest, walk-forward, shadow, paper, stored, delivered and executed categories remain distinct.
- Confirmed live drift uses only signals with Telegram-confirmed delivery evidence.

## Strategy framework coverage

The first production implementation is deliberately objective and conservative:

- ICT/SMC: confirmed pivots, structure breaks, liquidity sweeps, displacement and fair-value gaps with zone lifecycle fields.
- Price action: context-aware engulfing, pin rejection, inside/outside bars and breakouts.
- Supply/demand: rally/drop-base structures, departure strength, touch count and freshness.
- Fibonacci: confirmed swing anchors and golden-pocket confluence without future pivot access.
- Harmonics: ratio-validated Gartley, Bat, Butterfly, Crab, Cypher and AB=CD families.
- Elliott Wave: probabilistic pivot sequences and alternative counts; no forced definitive count.
- Order flow: genuine bid/ask or delta evidence only; candle volume is never presented as real order flow.
- Wyckoff: conservative spring/upthrust and incomplete classification support.
- Indicators: contextual evidence from existing calculated indicators, not a universal parameter claim.

## Promotion lifecycle

```text
SHADOW
→ FORWARD_TEST
→ CANARY
→ LIMITED_LIVE
```

Each step requires the next valid transition, at least 100 out-of-sample observations, at least three positive WFO folds, positive expectancy, profit factor of at least 1.10, drawdown no greater than 10R, acceptable Brier calibration, successful leakage checks, and an authenticated owner action. v1.1.0 intentionally does not expose a direct command to move a profile to unrestricted APPROVED live status.

## Automatic degradation response

Current CANARY/LIMITED_LIVE/APPROVED profiles are checked using Telegram-confirmed live evidence only. After the configured minimum sample count, excessive drawdown, materially negative expectancy, or poor calibration causes:

1. The current profile to enter `SUSPENDED`.
2. A drift event to be persisted.
3. Its recorded rollback profile to be restored when available.
4. Otherwise, the runtime to fall back to the neutral global baseline.
5. The stale Redis profile cache to be invalidated immediately.

## Railway and database safety

- Adaptive evaluation is synchronous CPU work inside the existing strategy thread; it does not acquire a database session.
- Candle capture is bounded and queued; the scan hot path does not wait on PostgreSQL.
- Learning runs use the analytics admission lane and a PostgreSQL advisory transaction lock.
- Provider, Telegram, Gemini, Redis and broker calls are not performed while an adaptive database session is open.
- Optimisation produces SHADOW candidates only.
- Profile publication reads in a short database session, closes it, then writes Redis.

## Known limitations and required evidence

- The initial candle-capture queue is process-local. It is safe for the current monolithic `RUN_MODE=all`; a split engine/analytics deployment should move capture events to a dedicated Redis Stream before scaling independently.
- Profile reliability depends on historical sequence coverage. Earlier signals created before v1.1.0 may have outcomes but no adaptive sequence references.
- Genuine Level 2/order-book history is not available from every free provider; order-flow components safely report unavailable in those cases.
- Elliott and Wyckoff interpretations remain probabilistic and must accumulate asset-specific evidence before promotion.
- Brier calibration must be present before owner promotion succeeds. The system deliberately blocks promotion when calibration is missing.
- No live profitability, minimum win rate, or production trading advantage is claimed by this release.
- Real-money auto-trading, copy trading, public payments and payouts remain independent systems and require their own certification.
