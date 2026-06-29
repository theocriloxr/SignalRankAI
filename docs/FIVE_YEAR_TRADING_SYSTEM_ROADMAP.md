# Five-Year Trading System Roadmap

Last updated: 2026-06-29

This roadmap captures the next durable upgrades for SignalRankAI after the
Railway monolith production pass. It is intentionally evidence-based: features
should graduate to production only when they have tests, telemetry, dry-run
history, and rollback controls.

## References Reviewed

- SEC market access risk controls, Rule 15c3-5:
  https://www.sec.gov/files/rules/final/2010/34-63241.pdf
- Binance Spot API order filters:
  https://developers.binance.com/docs/binance-spot-api-docs/filters
- Binance Spot API self-trade prevention:
  https://developers.binance.com/docs/binance-spot-api-docs/faqs/stp_faq
- Bybit V5 create-order API:
  https://bybit-exchange.github.io/docs/v5/order/create-order
- MetaTrader 5 Python integration:
  https://www.mql5.com/en/docs/python_metatrader5
- Alpaca paper trading:
  https://docs.alpaca.markets/docs/paper-trading
- MLflow model registry:
  https://mlflow.org/docs/latest/ml/model-registry/
- NIST AI Risk Management Framework:
  https://www.nist.gov/itl/ai-risk-management-framework

## Implemented In This Pass

### Score Calibration And Explainability

- Replaced hard high-score clipping with soft high-score compression.
- Added raw/calibrated score audit fields.
- Added score component metadata so the bot can explain why a signal scored
  well instead of only displaying a final number.
- Fixed engine and Telegram score resolvers so auxiliary fields do not inflate
  `max_score`.

### Regression Coverage

- Added tests proving high raw scores no longer flatten to exactly `100`.
- Added tests proving calibrated score fields win over auxiliary `100` fields.
- Re-ran delivery, command, callback, execution-safety, broker-permission, and
  production-readiness checks.

## Highest-Value Next Builds

### 1. Pre-Trade Risk Firewall

Goal: broker-independent risk controls before any paper, copy, or live order.

Features:

- Max notional per user, tier, asset class, symbol, broker, and day.
- Max daily loss and max open risk in R.
- Max correlated exposure by asset class, currency, sector, and beta cluster.
- Symbol allow/deny lists per broker and user.
- Broker filter validation before order placement:
  - Binance tick size, step size, min notional, max orders.
  - Bybit quantity, price, reduce-only, TP/SL mode, and category constraints.
  - MT5 volume step, filling mode, symbol trade mode, stops level, freeze level.
- Idempotent risk decision ledger with `approved`, `blocked`, `reduced`, and
  `manual_review` states.

Production gate:

- 30 days of shadow-mode decisions with zero unexpected live-order mismatches.

### 2. Broker Capability Matrix

Goal: every broker adapter exposes what it can safely do before execution.

Fields:

- `supports_market_order`
- `supports_limit_order`
- `supports_tp_sl_attach`
- `supports_reduce_only`
- `supports_position_mode`
- `supports_sandbox`
- `supports_order_preview`
- `min_notional_source`
- `fees_source`
- `latency_budget_ms`

Usage:

- Route copy/live trades only when the signal requirements match the broker
  capability profile.
- Degrade gracefully to alert-only mode when a broker cannot enforce required
  controls.

### 3. Paper/Live Parity Harness

Goal: paper trading should behave like the connected broker as closely as
possible.

Features:

- Broker-specific fee, spread, slippage, and partial-fill models.
- Order lifecycle parity: submitted, accepted, partially filled, filled,
  canceled, rejected, expired.
- Paper replay from historical signals and actual broker candles.
- Daily paper/live divergence report.

Production gate:

- Paper/live simulated fills remain within configured slippage tolerance for
  at least 500 shadow executions.

### 4. Outcome Coverage Recovery

Goal: never trust win rate until enough delivered signals have outcomes.

Features:

- Outcome coverage SLO by asset class and tier.
- Alert when coverage falls below 80%.
- Backfill priority queue for delivered-but-untracked signals.
- Distinguish `pending`, `stale`, `failed_delivery`, `expired`, `manual_close`,
  `tp1`, `tp2`, `tp3`, `partial_tp`, and `sl`.
- Expected win-rate report should show confidence intervals and sample size.

Production gate:

- At least 80% outcome coverage over 30 days before publishing expected win
  rate as a product metric.

### 5. Walk-Forward And Regime Validation

Goal: improve signal quality without overfitting.

Features:

- Rolling walk-forward optimization per asset class.
- Regime-specific strategy weights.
- Out-of-sample holdout by date and market condition.
- Monte Carlo risk-of-ruin from actual R-multiple distribution.
- Promotion policy: strategy weights increase only after out-of-sample proof.

Production gate:

- Every strategy weight change must include before/after expectancy and
  drawdown evidence.

### 6. Model Registry And Champion/Challenger ML

Goal: make ML changes auditable and reversible.

Features:

- Model version registry with feature schema hash.
- Champion/challenger shadow predictions.
- Drift metrics by asset class and timeframe.
- Auto-rollback when live calibration or Brier score degrades.
- Training data lineage: candle provider, signal version, outcome version.

Production gate:

- New model cannot become champion without passing shadow evaluation and
  schema compatibility checks.

### 7. Data Quality And Provider Reconciliation

Goal: avoid bad trades from stale or divergent market data.

Features:

- Candle freshness SLO per provider, asset class, and timeframe.
- Cross-provider price divergence checks.
- Corporate-action awareness for equities.
- Market-hours calendar per stocks, ETFs, FX, commodities, indices, and crypto.
- Provider outage routing with clear fail-open/fail-closed policy by asset.

Production gate:

- Signals are blocked or downgraded when provider disagreement exceeds the
  configured threshold.

### 8. Portfolio Intelligence

Goal: optimize ROI at portfolio level, not just per-signal score.

Features:

- Correlation-aware signal throttling.
- Exposure heatmap by base currency, quote currency, sector, region, and
  volatility cluster.
- Portfolio Kelly cap with conservative fractional sizing.
- Expected value ranking that combines win probability, R/R, fees, slippage,
  liquidity, spread, and holding period.

Production gate:

- Portfolio-level net R and drawdown improve in backtest and shadow mode before
  increasing live risk.

### 9. User Trust And Audit Ledger

Goal: every signal and trade decision can be explained after the fact.

Features:

- Immutable decision ledger for generated, rejected, delivered, executed, and
  closed signals.
- Human-readable signal explanation with top positive and negative factors.
- Admin replay command for a signal reference ID.
- User export for paper/live trade history.

Production gate:

- Any delivered or executed signal can be reconstructed from stored inputs,
  score components, risk decision, broker decision, and outcome.

## Recommended Execution Order

1. Pre-trade risk firewall.
2. Broker capability matrix.
3. Outcome coverage recovery.
4. Paper/live parity harness.
5. Data quality reconciliation.
6. Walk-forward and regime validation.
7. Model registry and champion/challenger ML.
8. Portfolio intelligence.
9. User trust and audit ledger.

