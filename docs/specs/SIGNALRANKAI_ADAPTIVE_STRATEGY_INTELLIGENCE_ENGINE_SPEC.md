# SIGNALRANKAI ADAPTIVE STRATEGY INTELLIGENCE ENGINE

## Production Implementation, Integration, Validation, and Continuous-Learning Prompt

## Role and Operating Mandate

Act as a senior quantitative trading systems engineer, algorithmic strategy researcher, machine-learning engineer, market-data architect, risk-management engineer, cybersecurity auditor, database engineer, and production software maintainer.

You are working directly on the existing **SignalRankAI** codebase.

SignalRankAI is a Telegram-first, multi-asset trading-intelligence platform that scans multiple asset classes and timeframes, generates and ranks trading opportunities, applies deterministic rules, optional ML and Gemini validation, risk controls, subscription and user-tier restrictions, delivery eligibility rules, signal lifecycle tracking, outcome tracking, paper evaluation, shadow evaluation, and Railway deployment infrastructure.

Your assignment is to design, implement, integrate, test, and document an **Adaptive Asset-Specific Strategy Intelligence Engine** that learns from complete historical and live market behaviour.

This module must improve the existing project without replacing, weakening, bypassing, or breaking any functionality that is already correctly implemented.

You must work on the real repository and deliver production-grade implementation—not only recommendations, architecture diagrams, pseudocode, TODO comments, placeholder services, disconnected experimental scripts, or simulated claims.

---

# 1. Primary Objective

Add an adaptive learning and strategy-optimisation capability to SignalRankAI where the system studies historical and ongoing market behaviour and progressively creates, selects, combines, tunes, validates, and improves custom strategies:

* Per individual asset.
* Per asset class.
* Per behavioural asset cluster.
* Per market regime.
* Per trading session.
* Per timeframe combination.
* Per volatility and liquidity condition.

Examples include specialised profiles for:

* BTC/USDT.
* ETH/USDT.
* SOL/USDT.
* EUR/USD.
* GBP/USD.
* XAU/USD.
* US30.
* NASDAQ.
* SPX.
* AAPL.
* NVDA.
* Other supported assets.

The engine must learn from **all relevant candle data and market sequences**, not only whether a delivered trade eventually won or lost.

It must understand:

* What happened before the setup.
* What happened when the setup formed.
* What happened between entry and exit.
* Why the setup succeeded or failed.
* Whether the direction was correct but the entry was poor.
* Whether the stop was too tight.
* Whether the target was unrealistic.
* Whether the signal was generated too early or too late.
* Whether the trade failed because of market regime, spread, slippage, execution, stale data, provider failure, news, or strategy logic.
* Whether a rejected or shadow signal would have performed better than a delivered signal.

The final system must produce measurable, reproducible, risk-adjusted improvement without fabricating profitability or weakening existing safety rules.

---

# 2. Additive Integration Requirement

Everything in this prompt is an addition to the existing SignalRankAI project.

Do not remove or replace working features merely to simplify the new implementation.

Preserve and integrate with the existing:

* Signal-generation pipeline.
* Multi-asset scanning.
* Multi-timeframe analysis.
* Deterministic strategy engine.
* Existing scoring and ranking system.
* ML validation.
* Gemini validation.
* News intelligence.
* Market-regime filters.
* Risk engine.
* Position-sizing logic.
* Signal delivery rules.
* Telegram bot.
* Telegram webhook handling.
* Commands and callback handlers.
* Subscription tiers.
* User eligibility rules.
* Redis queues and caches.
* PostgreSQL persistence.
* Worker architecture.
* Scheduler jobs.
* Provider failover.
* Signal deduplication.
* User-level delivery cooldowns.
* Shadow tracking.
* Outcome tracking.
* False-negative analysis.
* Correct-block analysis.
* Paper-trading evidence.
* Backtesting.
* Walk-forward testing.
* Deployment and diagnostic tooling.
* Administrative controls.
* Audit and governance registers.

When an existing component is incomplete or defective, repair and extend it instead of creating a separate competing implementation.

---

# 3. Mandatory Repository Audit

Before implementing the new engine, inspect the complete repository and reconstruct the actual runtime behaviour.

Identify and document:

1. All market-data providers.
2. REST and WebSocket ingestion paths.
3. Asset-universe selection.
4. Asset-class definitions.
5. Timeframe support.
6. Candle storage.
7. Candle normalisation.
8. Feature calculations.
9. Existing strategies.
10. Regime detection.
11. Signal generation.
12. Signal scoring.
13. ML validation.
14. Gemini validation.
15. News validation.
16. Risk validation.
17. Position sizing.
18. Deduplication.
19. Cooldowns.
20. Queueing.
21. Telegram delivery.
22. User-tier eligibility.
23. Broker or execution integrations.
24. Shadow processing.
25. Outcome tracking.
26. False-negative tracking.
27. Correct-block tracking.
28. Partial-win tracking.
29. Signal expiry.
30. Trade lifecycle processing.
31. Database models.
32. Database migrations.
33. Redis keys, streams, queues, locks, and counters.
34. Scheduler jobs.
35. Worker processes.
36. Administrative endpoints and commands.
37. Logging and tracing.
38. Deployment configuration.
39. Test coverage.
40. Current release gates.

Trace at least one complete signal through:

```text
Raw market data
→ normalisation
→ feature generation
→ strategy evaluation
→ confluence scoring
→ regime checks
→ ML validation
→ Gemini validation
→ news validation
→ risk validation
→ deduplication
→ user eligibility
→ queueing
→ Telegram delivery
→ optional execution
→ lifecycle monitoring
→ outcome classification
→ learning feedback
```

Produce a verified implementation map showing:

* Existing components to reuse.
* Components requiring modification.
* Missing components.
* Duplicate components.
* Disconnected components.
* Unsafe components.
* Deprecated components.
* Database changes.
* New services.
* New background jobs.
* Required tests.
* Migration and rollback requirements.

Do not begin large-scale implementation based only on filenames or assumptions.

---

# 4. Fundamental Learning Requirement

## 4.1 Do Not Learn Only From Win/Loss or PnL

The engine must not reduce a signal to only:

* Win.
* Loss.
* Break-even.
* Profit.
* Loss amount.
* TP reached.
* SL reached.

For every generated signal, capture and evaluate the complete price path.

This applies to:

* Delivered signals.
* Stored signals.
* Paper signals.
* Shadow signals.
* Backtest signals.
* Walk-forward signals.
* Rejected signals.
* Expired signals.
* Cancelled signals.
* Executed signals.
* Live-delivered signals.

These evidence categories must remain separate. Do not mix synthetic, paper, shadow, backtest, forward-test, owner-beta, or live evidence.

## 4.2 Required Pre-Signal Context

Capture the configurable number of candles before each signal across all relevant timeframes.

Analyse:

* Existing trend.
* Market structure.
* Swing highs and lows.
* Consolidation.
* Compression.
* Expansion.
* Volume behaviour.
* Volatility.
* Liquidity zones.
* Support and resistance.
* Premium and discount location.
* Session.
* Day of week.
* Correlated-market behaviour.
* News context.
* Higher-timeframe alignment.
* Spread and liquidity quality.
* Provider freshness.
* Market regime.
* Previous failed or successful setups in the same area.

## 4.3 Required In-Trade Context

Track:

* Intended entry.
* Realistically executable entry.
* Entry delay.
* Entry slippage.
* Spread.
* Maximum favourable excursion.
* Maximum adverse excursion.
* Time to first favourable movement.
* Time to first adverse movement.
* Time to TP1.
* Time to TP2.
* Time to TP3.
* Time to stop loss.
* Partial target sequence.
* Break-even movement.
* Trailing-stop behaviour.
* Liquidity sweeps after entry.
* Regime changes after entry.
* Volatility changes.
* News events during the trade.
* Correlated-market changes.
* Whether entry was missed.
* Whether price moved without filling the intended entry.
* Whether stop loss and take profit were both touched inside the same candle.

Same-candle TP and SL ambiguity must use a conservative, documented, configurable execution rule.

## 4.4 Required Post-Trade Context

Continue studying candles after closure to determine:

* Whether the direction remained correct after a premature stop.
* Whether the target was too close.
* Whether the trade exited too early.
* Whether the stop was too wide.
* Whether the move completely reversed.
* Whether a different timeframe would have produced a better entry.
* Whether the same setup repeated.
* Whether post-exit continuation justified trailing logic.
* Whether a winning trade was actually poorly structured and benefited from luck.
* Whether a losing trade had a valid thesis but failed because of execution or unexpected market behaviour.

---

# 5. Technical Analysis Framework Library

Implement the following frameworks as modular, testable, typed strategy components.

Each component must return structured evidence, not only a boolean signal.

Each result must include where applicable:

* Direction.
* Confidence.
* Setup type.
* Relevant price zones.
* Entry range.
* Stop-loss proposal.
* Take-profit proposals.
* Invalidation criteria.
* Timeframe.
* Regime suitability.
* Feature values.
* Data quality.
* Evidence timestamp.
* Explanation fields.
* Strategy version.
* Duplicate fingerprint.

## 5.1 ICT and Smart Money Concepts

Implement objective, configurable detection for:

* Break of Structure.
* Change of Character.
* Market Structure Shift.
* Internal structure.
* External structure.
* Buy-side liquidity.
* Sell-side liquidity.
* Equal highs.
* Equal lows.
* Previous-day highs and lows.
* Previous-week highs and lows.
* Session highs and lows.
* Liquidity sweeps.
* Liquidity grabs.
* Displacement.
* Order blocks.
* Bullish and bearish order blocks.
* Mitigated and unmitigated order blocks.
* Breaker blocks.
* Mitigation blocks.
* Fair value gaps.
* Inverse fair value gaps.
* Balanced price ranges.
* Premium and discount zones.
* Optimal trade entry zones.
* Judas swings where objectively definable.
* Session and kill-zone behaviour where suitable.

Every detected zone must have a lifecycle:

```text
Created
→ confirmed
→ active
→ partially mitigated
→ fully mitigated
→ invalidated
→ expired
→ archived
```

Avoid endlessly reusing stale or invalidated zones.

## 5.2 Price Action

Implement:

* Swing structure.
* Trend structure.
* Support and resistance.
* Role reversal.
* Break-and-retest.
* Rejection candles.
* Engulfing behaviour.
* Pin bars.
* Inside bars.
* Outside bars.
* Momentum candles.
* Compression.
* Expansion.
* False breakouts.
* Failed breakdowns.
* Trendline liquidity.
* Channels.
* Range boundaries.
* Multi-touch levels.
* Candle body and wick analysis.
* Impulse and correction quality.

Candlestick patterns must be evaluated in context. A candle pattern alone must not automatically create a high-confidence signal.

## 5.3 Elliott Wave

Implement probabilistic Elliott Wave analysis with:

* Impulse sequences.
* Corrective sequences.
* Zigzags.
* Flats.
* Expanded flats.
* Running flats where defensible.
* Triangles.
* Diagonals.
* Extensions.
* Truncations.
* Wave-degree management.
* Fibonacci wave relationships.
* Structural invalidation.
* Alternative wave counts.
* Confidence ranking.

Do not force a single definitive wave count when several counts remain possible.

Preserve alternative counts and record why one is preferred.

## 5.4 Order Flow

Where genuine order-flow data is available, support:

* Bid/ask delta.
* Cumulative delta.
* Footprint imbalance.
* Absorption.
* Exhaustion.
* Aggressive buying and selling.
* Passive liquidity.
* Volume profile.
* Point of control.
* Value Area High.
* Value Area Low.
* High-volume nodes.
* Low-volume nodes.
* Auction acceptance.
* Auction rejection.
* Initiative activity.
* Responsive activity.

Where genuine bid/ask or Level 2 data is not available:

* Use clearly labelled approximations only.
* Record the data source and confidence.
* Do not present candle volume as genuine order-flow data.
* Do not fabricate delta, absorption, or order-book evidence.

The strategy must degrade safely when order-flow data is unavailable.

## 5.5 Supply and Demand

Implement:

* Rally-base-rally.
* Drop-base-drop.
* Rally-base-drop.
* Drop-base-rally.
* Fresh supply zones.
* Fresh demand zones.
* Tested zones.
* Zone touch count.
* Zone freshness.
* Departure strength.
* Base quality.
* Compression into a zone.
* Higher-timeframe zone alignment.
* Zone invalidation.
* Zone expiry.
* Zone overlap resolution.
* Liquidity located around zones.

## 5.6 Fibonacci

Implement:

* Retracements.
* Extensions.
* Expansions.
* Projections.
* Fibonacci clusters.
* Time relationships only where statistically justified.
* Confluence with market structure.
* Confluence with liquidity.
* Confluence with Elliott Wave.
* Confluence with harmonic patterns.
* Configurable tolerances.
* Objective swing-anchor selection.
* Anchor invalidation.

Do not draw Fibonacci levels from arbitrary or future-confirmed swing points.

## 5.7 Harmonic Patterns

Implement validated detection for:

* Gartley.
* Bat.
* Alternate Bat.
* Butterfly.
* Crab.
* Deep Crab.
* Cypher.
* Shark.
* ABCD.
* Alternate AB=CD.

Each detected pattern must contain:

* X, A, B, C, and D points.
* Ratio calculations.
* Ratio tolerance.
* Potential Reversal Zone.
* Completion status.
* Entry range.
* Invalidation.
* Stop proposal.
* Target projections.
* Pattern maturity.
* Duplicate suppression.
* Overlap resolution.
* Historical reliability for the asset and regime.

## 5.8 Wyckoff

Implement:

* Accumulation.
* Distribution.
* Reaccumulation.
* Redistribution.
* Phase A.
* Phase B.
* Phase C.
* Phase D.
* Phase E.
* Preliminary support.
* Preliminary supply.
* Selling climax.
* Buying climax.
* Automatic rally.
* Automatic reaction.
* Secondary tests.
* Springs.
* Upthrusts.
* Upthrust after distribution.
* Signs of strength.
* Signs of weakness.
* Last points of support.
* Last points of supply.
* Range boundaries.
* Effort-versus-result behaviour.
* Volume-and-spread analysis.

Do not force every consolidation into a complete Wyckoff schematic.

Allow incomplete or uncertain classifications.

## 5.9 Indicator-Based Strategies

Support current project indicators and add modular versions of:

* EMA.
* SMA.
* WMA.
* VWAP.
* Anchored VWAP.
* RSI.
* Stochastic RSI.
* MACD.
* Bollinger Bands.
* Keltner Channels.
* ATR.
* ADX.
* Supertrend.
* Ichimoku.
* Rate of Change.
* Momentum.
* Volume indicators.
* Custom oscillators already present in SignalRankAI.

Indicators must be configurable per asset, timeframe, session, and regime.

Do not assume one universal setting such as RSI 14, EMA 20, or EMA 200 is optimal for every instrument.

---

# 6. Strategy Component Interface

Create a shared strategy-component interface similar in responsibility to:

```python
class StrategyComponent(Protocol):
    strategy_id: str
    version: str

    async def evaluate(
        self,
        context: MarketContext,
        profile: AssetStrategyProfile,
    ) -> StrategyEvidence:
        ...
```

The actual interface must follow the project’s architecture and typing conventions.

The returned structure should include:

```python
StrategyEvidence(
    strategy_id=...,
    strategy_version=...,
    asset=...,
    asset_class=...,
    timeframe=...,
    direction=...,
    setup_type=...,
    confidence=...,
    raw_score=...,
    zones=...,
    entry_proposal=...,
    stop_proposal=...,
    target_proposals=...,
    invalidation=...,
    regime_compatibility=...,
    data_quality=...,
    evidence=...,
    conflicts=...,
    duplicate_fingerprint=...,
)
```

Do not create a single oversized strategy file containing all methodologies.

---

# 7. Multi-Timeframe Intelligence

The engine must distinguish between:

* Bias timeframe.
* Structure timeframe.
* Setup timeframe.
* Confirmation timeframe.
* Entry timeframe.
* Execution timeframe.
* Outcome timeframe.

Example:

```text
1D directional bias
→ 4H market structure
→ 1H setup
→ 15M confirmation
→ 5M entry refinement
```

However, timeframe combinations must be learned per asset rather than hard-coded globally.

The optimiser should determine:

* Which higher timeframe provides useful bias.
* Which timeframe produces reliable structure.
* Which timeframe produces the best setup.
* Which timeframe gives the most realistic entry.
* Whether lower-timeframe refinement improves or worsens performance.
* Whether the asset performs better with single-timeframe strategies.

No higher-timeframe calculation may use candles that were not closed or available at the lower-timeframe decision timestamp.

---

# 8. Market-Regime Engine

Create or improve the regime-classification system to recognise:

* Strong bullish trend.
* Weak bullish trend.
* Strong bearish trend.
* Weak bearish trend.
* Sideways range.
* Accumulation.
* Distribution.
* Reaccumulation.
* Redistribution.
* Breakout.
* Failed breakout.
* Post-breakout expansion.
* Low-volatility compression.
* High-volatility expansion.
* Mean-reversion regime.
* Momentum regime.
* Illiquid regime.
* Abnormal spread regime.
* News-driven regime.
* Risk-on environment.
* Risk-off environment.
* Correlation breakdown.
* Provider or data-quality uncertainty.

Every strategy must define:

* Allowed regimes.
* Preferred regimes.
* Penalised regimes.
* Disabled regimes.
* Minimum regime confidence.
* Behaviour during regime transitions.

The engine must be able to return:

```text
NO TRADE
```

when conditions are unsuitable.

It must not force a signal for every asset or scan cycle.

---

# 9. Asset-Specific Learning

Create a persistent, versioned strategy profile for every supported asset.

Each asset profile should store:

* Asset identity.
* Asset class.
* Data providers.
* Market hours.
* Preferred sessions.
* Avoided sessions.
* Preferred weekdays.
* Volatility profile.
* Liquidity profile.
* Spread profile.
* Gap behaviour.
* Typical trend persistence.
* Mean-reversion tendency.
* Breakout reliability.
* News sensitivity.
* Correlated instruments.
* Preferred strategy families.
* Penalised strategy families.
* Disabled strategy families.
* Preferred timeframe combinations.
* Entry requirements.
* Confirmation requirements.
* Stop methodology.
* Target methodology.
* Partial-exit rules.
* Break-even rules.
* Trailing-stop rules.
* Setup expiry.
* Minimum confidence.
* Minimum reward-to-risk.
* Maximum signal frequency.
* Recommended cooldown.
* Average holding duration.
* Regime-specific performance.
* Session-specific performance.
* Direction-specific performance.
* Confidence calibration.
* Data-sufficiency score.
* Last training timestamp.
* Last evaluation timestamp.
* Current approved profile version.
* Previous approved version.
* Rollback version.

The profile must be explainable and auditable.

No asset profile should be considered reliable until minimum data and validation requirements are met.

---

# 10. Asset-Class and Behavioural Clustering

Support the existing SignalRankAI asset classes, including:

* Cryptocurrency.
* Forex.
* Commodities.
* Equities.
* Indices.
* Any other currently supported class.

Create a hierarchical learning structure:

```text
Global baseline
→ asset-class baseline
→ behavioural-cluster baseline
→ individual asset profile
→ regime-specific asset profile
```

Cluster assets using validated characteristics such as:

* Volatility.
* Liquidity.
* Trend persistence.
* Mean-reversion tendency.
* Session behaviour.
* Spread.
* Gap behaviour.
* Momentum.
* Correlation.
* Average trade duration.
* News sensitivity.

Knowledge transfer must be controlled.

Do not assume that all cryptocurrencies behave alike or that all forex pairs use the same strategy.

Individual asset evidence must override asset-class assumptions once enough reliable data exists.

Prevent negative transfer between structurally different assets.

---

# 11. Strategy Specification and Registry

Represent each strategy or profile as a validated, versioned machine-readable specification.

Each strategy specification must include:

* Strategy ID.
* Strategy name.
* Strategy family.
* Version.
* Parent version.
* Creation source.
* Supported assets.
* Supported asset classes.
* Supported regimes.
* Timeframe hierarchy.
* Feature requirements.
* Entry rules.
* Confirmation rules.
* Filter rules.
* Invalidation rules.
* Stop-loss logic.
* Take-profit logic.
* Scaling rules.
* Trailing rules.
* Expiry rules.
* Risk multiplier.
* Confidence calibration.
* Data-quality requirements.
* Training dataset version.
* Feature-set version.
* Backtest evidence.
* Walk-forward evidence.
* Shadow evidence.
* Forward-test evidence.
* Live evidence where available.
* Approval state.
* Approver.
* Approval timestamp.
* Suspension reason.
* Rollback version.

Do not generate arbitrary executable strategy code using Gemini or another language model and run it automatically.

AI may propose a structured candidate specification, but deterministic validators must reject unsupported, unsafe, malformed, or out-of-bounds rules.

---

# 12. Confluence and Evidence Scoring

Improve the existing SignalRankAI scoring system so it combines technical evidence without double-counting correlated features.

For example:

* EMA trend.
* MACD momentum.
* ADX trend strength.
* Higher-high structure.
* Break of Structure.

These may all describe related trend behaviour and must not automatically be treated as five fully independent confirmations.

The scoring engine must distinguish:

* Independent evidence.
* Correlated evidence.
* Duplicate evidence.
* Conflicting evidence.
* Missing evidence.
* Low-quality evidence.
* Estimated evidence.
* Genuine market evidence.

Consider:

* Higher-timeframe alignment.
* Structure quality.
* Regime compatibility.
* Liquidity context.
* Entry quality.
* Volume confirmation.
* Volatility suitability.
* Session suitability.
* Historical asset-specific reliability.
* Asset-class reliability.
* Strategy reliability.
* Direction-specific reliability.
* News risk.
* Spread.
* Slippage.
* Execution feasibility.
* Portfolio exposure.
* Model uncertainty.
* Data quality.
* Provider freshness.

Store separately:

* Raw strategy score.
* Deterministic confluence score.
* ML score.
* Gemini decision.
* News adjustment.
* Risk adjustment.
* Final delivery score.
* Calibrated confidence.
* Uncertainty.
* Rejection reason.

Do not allow Gemini to silently replace deterministic scoring.

---

# 13. Gemini and ML Integration

Gemini and ML already influence parts of SignalRankAI, including confidence, ranking, risk, position size, validation, and explanation.

Preserve this architecture while making it safer and more measurable.

Gemini must:

* Consume structured market evidence.
* Return schema-validated structured output.
* Explain evidence that actually exists.
* Identify contradictions.
* Flag uncertainty.
* Suggest bounded adjustments.
* Respect timeouts and circuit breakers.
* Degrade safely when unavailable.

Gemini must not:

* Invent price levels.
* Invent indicators.
* Invent news.
* Invent market structure.
* Invent order flow.
* Fabricate confidence.
* generate a live signal without deterministic evidence.
* bypass risk controls.
* bypass delivery eligibility.
* alter persistent strategy profiles without validation and approval.

ML models must have:

* Versioned datasets.
* Versioned features.
* Versioned models.
* Reproducible training.
* Chronological validation.
* Calibration.
* Drift monitoring.
* Rollback support.
* Safe fallback behaviour.

When Gemini or ML is unavailable, the deterministic engine must continue safely according to explicit configuration.

---

# 14. Continuous Strategy Evolution

Implement a controlled strategy-improvement loop:

```text
Collect market and signal data
→ validate data quality
→ construct reproducible datasets
→ generate features
→ analyse historical sequences
→ create candidate profiles
→ backtest
→ perform walk-forward validation
→ test across regimes
→ model spread, fees, slippage and latency
→ perform parameter-stability testing
→ compare against current champion
→ register candidate
→ run in shadow mode
→ run controlled forward test
→ canary promotion
→ limited live approval
→ monitor degradation
→ retain, suspend or roll back
```

The engine may use:

* Constrained grid search.
* Random search.
* Bayesian optimisation.
* Evolutionary optimisation.
* Multi-objective optimisation.
* Contextual bandits for bounded strategy selection.
* Supervised learning.
* Unsupervised clustering.
* Online updating with strict safety limits.

Prefer simpler and more stable candidates over unnecessarily complex models.

---

# 15. Champion–Challenger Architecture

Every asset must have:

* One approved champion profile.
* Zero or more challenger profiles.
* A clear baseline.
* A fallback profile.
* A rollback profile.

A challenger must not replace the champion merely because of a higher in-sample return or win rate.

Compare candidates using:

* Out-of-sample expectancy.
* Profit factor.
* Drawdown.
* Risk-adjusted return.
* Calibration.
* Regime stability.
* Parameter stability.
* Slippage sensitivity.
* Trade count.
* Turnover.
* Session stability.
* Asset stability.
* Tail losses.
* Execution feasibility.

Use configurable minimum improvement margins.

Reject candidates that produce marginal gains with significantly greater complexity, turnover, risk, or fragility.

---

# 16. Anti-Overfitting and Data-Leakage Protection

Mandatory safeguards:

* Strict chronological splits.
* No random train-test splitting for time-series evaluation.
* Walk-forward validation.
* Purged validation where trade labels overlap.
* Embargo periods where required.
* No future candle access.
* No future swing-point leakage.
* No future regime labels.
* No use of revised data that was unavailable at the decision time.
* No final-test-set optimisation.
* No repeated test-set peeking.
* Realistic transaction costs.
* Realistic spread.
* Realistic slippage.
* Realistic latency.
* Missing-candle simulation.
* Provider outage simulation.
* Multiple-regime evaluation.
* Parameter perturbation.
* Sensitivity testing.
* Monte Carlo or bootstrap testing where appropriate.
* Minimum trade-count requirements.
* Complexity penalties.
* Drawdown penalties.
* Turnover penalties.
* Multiple-hypothesis awareness.
* Survivorship-bias awareness.
* Delisted-symbol handling where relevant.

Reject brittle candidates that fail when parameters are changed slightly.

---

# 17. Optimisation Objectives

Do not optimise only for win rate.

Evaluate:

* Net expectancy.
* Profit factor.
* Sharpe ratio.
* Sortino ratio.
* Calmar ratio.
* Maximum drawdown.
* Average drawdown.
* Drawdown duration.
* Recovery factor.
* Win rate.
* Average win.
* Average loss.
* Payoff ratio.
* Median trade return.
* Tail loss.
* Value at Risk where useful.
* Conditional Value at Risk where useful.
* Maximum favourable excursion.
* Maximum adverse excursion.
* Time to target.
* Time to invalidation.
* Signal precision.
* False-positive rate.
* False-negative rate.
* Confidence calibration.
* Brier score.
* Turnover.
* Holding period.
* Spread sensitivity.
* Slippage sensitivity.
* Regime stability.
* Session stability.
* Asset stability.
* Capacity constraints.

A strategy with a lower win rate but better expectancy and controlled drawdown may be better than one with a high win rate and severe tail risk.

Do not promise or hard-code a minimum 60% win rate.

---

# 18. Shadow and Counterfactual Learning

Integrate fully with SignalRankAI’s shadow and outcome-tracking architecture.

Track signals rejected because of:

* Score.
* Regime.
* Squeeze.
* Microstructure.
* ML validation.
* Gemini validation.
* News.
* Risk.
* Data quality.
* Provider freshness.
* Duplicate detection.
* Cooldown.
* User-tier restrictions.
* Subscription status.
* Portfolio exposure.
* Execution infeasibility.
* Missing market data.
* Circuit-breaker activation.

Classify their later outcomes as:

* Correct block.
* False negative.
* Avoided loss.
* Missed winner.
* Correct direction but poor entry.
* Correct setup but poor stop.
* Correct setup but poor target.
* Late signal.
* Premature signal.
* Regime mismatch.
* Data failure.
* Provider failure.
* Execution failure.
* Insufficient evidence.

Do not automatically weaken a safety rule because some blocked signals later won.

Safety controls and strategy-quality controls must be analysed separately.

---

# 19. Signal Lifecycle Separation

Preserve strict evidence separation between:

* Generated.
* Stored.
* Eligible.
* Rejected.
* Queued.
* Delivered.
* Telegram-confirmed delivered.
* Paper.
* Shadow.
* Backtest.
* Walk-forward.
* Forward-test.
* Canary.
* Owner-beta.
* Live-delivered.
* Live-executed.
* Expired.
* Cancelled.
* Closed.

Never report generated signals as delivered signals.

Never report backtest evidence as live evidence.

Never use shadow results as proof of live profitability.

Never claim production readiness from unit tests alone.

---

# 20. Risk-Management Supremacy

The adaptive engine must remain subordinate to the existing SignalRankAI risk engine.

It must never silently override:

* Maximum risk per trade.
* Maximum daily loss.
* Maximum portfolio loss.
* Maximum drawdown.
* Position-size limits.
* Leverage limits.
* Correlation limits.
* Exposure limits.
* Asset limits.
* Asset-class limits.
* Broker limits.
* Subscription-tier limits.
* Trading-mode limits.
* Compliance restrictions.
* Kill switches.
* Emergency stops.
* Owner-only controls.

The adaptive engine may recommend bounded risk multipliers, but all recommendations must pass deterministic validation.

Add portfolio awareness for:

* Multiple crypto positions with the same market beta.
* USD concentration across forex pairs.
* Index and constituent overlap.
* Equity-sector concentration.
* Commodity correlation.
* Same-direction exposure.
* Volatility concentration.
* Multiple strategies representing the same underlying thesis.

A high-confidence trade must still be rejected when portfolio risk is unacceptable.

---

# 21. Signal Deduplication and Delivery Frequency

Preserve the existing SignalRankAI delivery cooldown requirement:

> After a specific asset has been sent to a particular user, another signal for that asset must not be sent to the same user for at least four hours unless an explicitly validated replacement or emergency update rule applies.

Implement or preserve:

* Per-user and per-asset cooldown.
* Per-user, per-asset, and per-direction cooldown.
* Per-user, per-asset, and per-timeframe cooldown.
* Strategy cooldown.
* Global asset cooldown.
* Setup fingerprinting.
* Zone fingerprinting.
* Similar-entry detection.
* Duplicate direction detection.
* Signal replacement rules.
* Signal upgrade rules.
* Cancellation messages.
* Invalidation messages.
* Distributed locking.
* Multi-worker-safe atomic enforcement.

Do not let different strategies repeatedly send what is effectively the same market opportunity.

Persist the reason a signal was considered duplicate, upgraded, replaced, delayed, or blocked.

---

# 22. Data Architecture

Create or improve canonical storage for:

* Assets.
* Asset classes.
* Providers.
* Raw candles.
* Normalised candles.
* Candle-quality status.
* Data gaps.
* Feature sets.
* Feature versions.
* Market structures.
* Liquidity zones.
* Supply and demand zones.
* Harmonic patterns.
* Elliott counts.
* Wyckoff classifications.
* Market regimes.
* Strategy components.
* Strategy specifications.
* Strategy versions.
* Asset profiles.
* Asset-class profiles.
* Behavioural clusters.
* Optimisation runs.
* Dataset versions.
* Backtest runs.
* Walk-forward runs.
* Shadow runs.
* Forward-test runs.
* Promotion decisions.
* Signal evidence.
* Signal conflicts.
* Signal rejection reasons.
* Signal delivery status.
* Trade outcomes.
* Candle-path outcomes.
* Maximum favourable excursion.
* Maximum adverse excursion.
* Model versions.
* Calibration versions.
* Drift events.
* Suspension events.
* Rollbacks.
* Administrative audit logs.

Do not duplicate full candle sequences inside every signal row.

Reference canonical time-series records or compressed sequence stores.

Add appropriate:

* Foreign keys.
* Uniqueness constraints.
* Indexes.
* Composite indexes.
* Idempotency keys.
* Retention rules.
* Partitioning recommendations.
* Cleanup jobs.

All migrations must be rerunnable or safely guarded according to the project’s migration framework.

Do not use runtime `create_all()` as a substitute for proper production migrations.

---

# 23. Railway, PostgreSQL, Redis, and Worker Safety

Preserve the existing production architecture and verify its actual configuration.

Account for:

* Railway deployment.
* PostgreSQL.
* PgBouncer transaction pooling where configured.
* Redis queues.
* Redis caches.
* Redis Streams where used.
* Telegram webhook mode.
* Multiple workers.
* Scheduler processes.
* Provider calls.
* Gemini calls.
* Paystack calls where relevant.
* MetaApi, TradingView, or broker integrations where present.

Do not hold PostgreSQL sessions open while waiting for:

* Telegram.
* Providers.
* Gemini.
* Paystack.
* Redis.
* Broker APIs.
* External HTTP requests.

Avoid session-level PostgreSQL behaviour incompatible with transaction pooling.

Implement:

* Distributed locks.
* Idempotency.
* At-least-once queue safety.
* Safe acknowledgement.
* Retry limits.
* Dead-letter handling.
* Exponential backoff.
* Checkpointing.
* Restart recovery.
* Stale-job detection.
* Duplicate-job suppression.
* Graceful shutdown.
* Bounded concurrency.
* Backpressure.

Run optimisation and heavy feature-generation work separately from latency-sensitive Telegram delivery workers.

---

# 24. Provider and Data-Quality Resilience

SignalRankAI currently depends on free or rate-limited providers and may encounter provider restrictions or outages.

The adaptive engine must:

* Record the provider used for every candle.
* Detect stale candles.
* Detect missing candles.
* Detect duplicate candles.
* Detect impossible OHLC values.
* Detect timezone errors.
* Detect abnormal gaps.
* Detect volume anomalies.
* Compare multiple providers where available.
* Assign data-quality confidence.
* Fail over safely.
* Avoid mixing incompatible feeds silently.
* Track provider-specific biases.
* Suspend strategy evaluation when minimum data quality is not met.

Do not create signals from stale or corrupted data merely to keep the scan count high.

A provider outage must not be classified as a strategy failure.

---

# 25. News and Event Intelligence

Integrate with the existing news intelligence rather than creating an isolated news system.

For every signal, record:

* Relevant scheduled economic events.
* Relevant asset-specific news.
* Market-wide news.
* Event severity.
* Time until event.
* Time since event.
* Data-source confidence.
* Whether news caused a block, penalty, or risk reduction.

Separate:

* Technical setup quality.
* News risk.
* Provider risk.
* Execution risk.

The adaptive engine should learn whether an asset’s strategy performance changes around news, but it must not encourage unsafe trading simply because some historical news trades were profitable.

---

# 26. Explainability

Every generated, rejected, delivered, shadow, or executed signal must be explainable using real structured evidence.

Store:

* Asset profile.
* Profile version.
* Strategy components.
* Strategy versions.
* Detected regime.
* Higher-timeframe bias.
* Entry setup.
* Supporting evidence.
* Conflicting evidence.
* Liquidity context.
* Stop rationale.
* Target rationale.
* Invalidation.
* Data-quality status.
* Provider.
* Raw score.
* Calibrated confidence.
* ML result.
* Gemini result.
* News adjustment.
* Risk adjustment.
* Portfolio adjustment.
* Delivery decision.
* Rejection reason.
* Model uncertainty.

Gemini may convert this structured evidence into understandable text, but it must not invent technical justification.

---

# 27. Strategy Promotion Governance

Use controlled states such as:

```text
DRAFT
RESEARCH
BACKTEST_QUALIFIED
WALK_FORWARD_QUALIFIED
SHADOW
FORWARD_TEST
CANARY
LIMITED_LIVE
APPROVED
SUSPENDED
ROLLED_BACK
RETIRED
```

A strategy must never move directly from research or backtest into unrestricted live use.

Promotion rules must be configurable and require:

* Minimum data.
* Minimum trade count.
* Multiple regimes.
* Out-of-sample evidence.
* Acceptable drawdown.
* Acceptable calibration.
* Parameter stability.
* Cost-adjusted performance.
* Shadow evidence.
* Forward-test evidence.
* No unresolved safety defects.
* Human approval where configured.

Support automatic suspension when:

* Drawdown exceeds approved tolerance.
* Slippage is materially worse than expected.
* Confidence calibration degrades.
* Data quality deteriorates.
* Model drift is detected.
* Strategy behaviour differs materially from backtest.
* Error rates increase.
* Required providers fail.
* Trade frequency becomes abnormal.
* Duplicate-signal rate increases.
* Risk rejections spike unexpectedly.

Support immediate rollback to the previous approved version.

---

# 28. Public Release and Live-Trading Safety

Do not enable or expand the following merely because the adaptive strategy engine exists:

* Public real-money auto-trading.
* Copy trading.
* Unrestricted broker execution.
* Public payment acceptance.
* Public payouts.
* Fully automated strategy promotion.

These must remain behind independent configuration, security, compliance, operational, and live-evidence gates.

Owner-beta, paper, shadow, backtest, and live trading must remain separate modes.

Do not claim public production readiness until real Railway, Telegram, provider, database, Redis, and signal-lifecycle evidence has been captured.

---

# 29. Testing Requirements

## 29.1 Unit Tests

Test:

* Candle normalisation.
* Feature calculations.
* Swing detection.
* Structure detection.
* Liquidity detection.
* Order blocks.
* Fair value gaps.
* Supply and demand zones.
* Fibonacci anchors.
* Harmonic ratios.
* Elliott invalidation.
* Wyckoff classification.
* Indicator calculations.
* Regime classification.
* Strategy scoring.
* Evidence deduplication.
* Profile versioning.
* Optimisation constraints.
* Promotion rules.
* Rollback.
* Risk boundaries.
* Cooldowns.
* Four-hour per-user asset delivery blocking.
* Confidence calibration.
* Data-quality rules.

## 29.2 No-Look-Ahead Tests

Prove that:

* Future candles cannot be accessed.
* Future swing confirmation cannot leak into historical decisions.
* Higher-timeframe candles are only available when closed.
* Indicators use only available data.
* Regime labels do not use future information.
* Harmonic completion does not use future points.
* Elliott counts do not use future invalidation knowledge.
* Zone validity is determined only from information available at the timestamp.

## 29.3 Integration Tests

Test:

* Provider to candle store.
* Candle store to feature engine.
* Feature engine to strategy components.
* Components to confluence score.
* Score to ML.
* ML to Gemini.
* Gemini to news.
* News to risk.
* Risk to deduplication.
* Deduplication to user eligibility.
* User eligibility to queue.
* Queue to Telegram.
* Telegram result to delivery evidence.
* Delivery to outcome tracking.
* Outcome tracking to learning datasets.
* Optimisation to strategy registry.
* Strategy registry to shadow evaluation.
* Promotion to runtime profile selection.
* Rollback to previous strategy version.

## 29.4 Multi-Worker Tests

Simulate:

* Two workers generating the same signal.
* Two workers promoting the same strategy.
* Two workers updating the same outcome.
* Duplicate Telegram jobs.
* Duplicate Redis messages.
* Worker crash after processing but before acknowledgement.
* Database reconnect during a transaction.
* Redis restart.
* Scheduler duplication.
* Deployment restart.

## 29.5 Failure Tests

Simulate:

* Provider outage.
* Stale data.
* Missing candles.
* Partial candles.
* Redis failure.
* PostgreSQL failure.
* Gemini timeout.
* Gemini malformed output.
* Telegram timeout.
* News provider failure.
* Model-loading failure.
* Optimisation interruption.
* Corrupted dataset.
* Invalid strategy version.
* Rollback after bad canary performance.

---

# 30. Observability

Add structured metrics, logs, traces, and alerts for:

* Provider health.
* Candle freshness.
* Missing data.
* Feature latency.
* Strategy-evaluation latency.
* Signals generated.
* Signals eligible.
* Signals rejected.
* Rejection reasons.
* Duplicate blocks.
* Four-hour user cooldown blocks.
* Queue depth.
* Queue lag.
* Telegram send attempts.
* Telegram confirmed delivery.
* Delivery failures.
* Gemini latency.
* Gemini circuit-breaker status.
* ML latency.
* News latency.
* Shadow-signal count.
* False-negative count.
* Correct-block count.
* Partial-win count.
* Strategy performance.
* Strategy version.
* Asset-profile version.
* Calibration drift.
* Data drift.
* Drawdown.
* Slippage.
* Promotion.
* Suspension.
* Rollback.
* Kill-switch activation.

Every signal must have a stable correlation ID covering its complete lifecycle.

Do not log secrets, tokens, credentials, user passwords, broker keys, database URLs, Redis credentials, Telegram tokens, Paystack secrets, or private user information.

---

# 31. Administrative and Owner Controls

Provide secure controls for the project owner or authorised administrators to:

* View asset profiles.
* View asset-class profiles.
* Compare champion and challenger strategies.
* View strategy evidence.
* View optimisation runs.
* View walk-forward results.
* View shadow results.
* View live-versus-expected divergence.
* Approve promotion.
* Reject promotion.
* Pin a strategy version.
* Suspend a strategy.
* Suspend an asset.
* Suspend an asset class.
* Roll back a profile.
* Start or stop optimisation.
* Activate a kill switch.
* View drift alerts.
* Export audit evidence.
* View signal rejection analysis.
* View false-negative analysis.
* View provider-health status.

Administrative actions must be:

* Authenticated.
* Authorised.
* Audited.
* Idempotent.
* Protected against duplicate execution.

---

# 32. Required Deliverables

The task is not complete until you provide:

1. Full repository audit.
2. Verified current architecture.
3. Target architecture.
4. Gap analysis.
5. Threat and failure analysis.
6. Phased implementation plan.
7. Exact files to create.
8. Exact files to modify.
9. Complete production-grade code.
10. Database migrations.
11. Redis key and queue changes.
12. Environment-variable additions.
13. Configuration updates.
14. Backfill scripts.
15. Feature-generation scripts.
16. Dataset-building scripts.
17. Model-training scripts.
18. Backtest implementation.
19. Walk-forward implementation.
20. Shadow integration.
21. Promotion workflow.
22. Rollback workflow.
23. Unit tests.
24. Integration tests.
25. Failure tests.
26. Load tests.
27. Updated diagnostics.
28. Updated deployment configuration.
29. Monitoring and alert definitions.
30. Operational runbooks.
31. Developer documentation.
32. Strategy-development documentation.
33. Data dictionary.
34. Security notes.
35. Known limitations.
36. Actual command outputs and test evidence.
37. Final production-readiness scorecard.
38. Release package or patch where required.

Do not provide partial snippets when full files are necessary.

Do not claim completion when code exists but is not connected to the active runtime.

---

# 33. Required Implementation Phases

## Phase 1: Audit and Reconstruction

* Inspect the repository.
* Trace all signal paths.
* Identify current strategy logic.
* Map learning and outcome systems.
* Identify production defects.
* Define safe integration points.

## Phase 2: Data and Sequence Foundation

* Canonicalise candle data.
* Add quality validation.
* Add market-sequence storage.
* Add dataset versioning.
* Add feature versioning.
* Add historical backfill.
* Separate evidence categories.

## Phase 3: Strategy Framework Library

* Define shared interfaces.
* Migrate existing strategies.
* Add ICT and SMC.
* Add price action.
* Add Elliott Wave.
* Add order flow.
* Add supply and demand.
* Add Fibonacci.
* Add harmonic patterns.
* Add Wyckoff.
* Add indicator strategies.
* Add tests.

## Phase 4: Regime and Asset Intelligence

* Improve regime classification.
* Create asset-class profiles.
* Create behavioural clusters.
* Create asset-specific profiles.
* Add session intelligence.
* Add profile versioning.

## Phase 5: Backtesting and Optimisation

* Build or repair the event-driven backtester.
* Add realistic execution modelling.
* Add walk-forward validation.
* Add anti-overfitting controls.
* Add champion–challenger comparison.
* Add candidate registry.

## Phase 6: Shadow and Counterfactual Learning

* Integrate all rejected-signal categories.
* Track complete candle paths.
* Classify false negatives and correct blocks.
* Add shadow performance reports.
* Add learning-data validation.

## Phase 7: Runtime Integration

* Load only approved profiles.
* Apply asset-specific strategy selection.
* Preserve deterministic risk controls.
* Preserve ML and Gemini validation.
* Preserve news filtering.
* Preserve cooldowns.
* Preserve user-tier eligibility.
* Preserve Telegram delivery behaviour.

## Phase 8: Controlled Promotion

* Add forward testing.
* Add canary deployment.
* Add limited-live mode.
* Add approval workflow.
* Add automatic suspension.
* Add rollback.

## Phase 9: Production Hardening

* Add observability.
* Add multi-worker tests.
* Add outage tests.
* Add restart recovery.
* Add load testing.
* Add security review.
* Verify Railway behaviour.
* Verify PostgreSQL and Redis behaviour.
* Verify Telegram delivery.
* Verify complete signal lifecycle.

---

# 34. Definition of Done

The adaptive strategy engine is complete only when:

* It is connected to the actual SignalRankAI runtime.
* It learns from full candle sequences.
* It distinguishes strategy failure from provider, execution, news, and data failure.
* It supports all requested technical frameworks.
* Frameworks produce structured, testable evidence.
* Asset profiles are persistent and versioned.
* Asset-class learning is implemented safely.
* Behavioural clustering is implemented.
* Regime-specific strategy selection works.
* Backtesting is free from known look-ahead leakage.
* Walk-forward validation works.
* Costs and execution constraints are modelled.
* Shadow signals are tracked.
* Rejected signals are evaluated.
* Champion–challenger comparison works.
* Promotion gates work.
* Rollback works.
* Gemini cannot invent evidence.
* ML models are versioned and calibrated.
* Risk controls remain authoritative.
* Four-hour per-user asset cooldown remains enforced.
* Multi-worker duplicate delivery is prevented.
* Telegram delivery evidence is accurate.
* Generated, delivered, paper, shadow, and live evidence remain separate.
* Provider failures degrade safely.
* Tests pass.
* Deployment works.
* Documentation is complete.
* Actual production evidence is reported honestly.

---

# 35. Strict Prohibitions

Do not:

* Guarantee profitability.
* Guarantee a minimum win rate.
* Fabricate backtest results.
* Fabricate shadow results.
* Fabricate live results.
* Fabricate confidence scores.
* Use future data.
* Optimise against the final test set.
* Mix backtest and live evidence.
* Count generated signals as delivered signals.
* Treat proxy volume as genuine order flow.
* Let Gemini create unsupported market evidence.
* Let AI override deterministic risk controls.
* Auto-promote strategies from backtest results alone.
* Enable unrestricted real-money trading.
* Weaken safety rules because of isolated missed winners.
* Store secrets in source code.
* expose credentials in logs.
* Hold database sessions during external API waits.
* Create duplicate strategy engines.
* Leave TODOs in required production paths.
* Use placeholder functions.
* create disconnected database models.
* mark a feature complete without integration tests.
* claim production readiness from tests alone.
* remove working legacy functionality without a migration path.
* optimise solely for win rate.
* force signals when no valid setup exists.

---

# 36. Final Execution Instruction

Begin by auditing the complete SignalRankAI repository and documenting the actual current behaviour.

Do not immediately create a new isolated strategy module before understanding the existing architecture.

For every implementation phase:

1. State what currently exists.
2. Identify verified deficiencies.
3. Explain the selected design.
4. List exact files to create or modify.
5. Implement complete code.
6. Add migrations.
7. Add tests.
8. Run the tests.
9. Run relevant diagnostics.
10. Report actual outputs.
11. Update documentation and governance registers.
12. Record unresolved limitations honestly.
13. Continue until the feature is integrated end to end.

The final product must be a cohesive extension of SignalRankAI that continuously develops safer, more robust, regime-aware, asset-specific strategies from complete historical and ongoing market behaviour.

It must not become a disconnected collection of indicators, experimental notebooks, unvalidated AI suggestions, or overfitted backtest configurations.
