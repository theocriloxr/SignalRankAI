You are working directly on my existing **SignalRankAI** repository.

Your task is to perform a full repository-aware implementation of the research, backtesting, statistical-validation, anti-overfitting, risk, strategy-health, and production-monitoring improvements described below.

You must also independently read, analyze, and extract useful concepts from this Google Doc:

https://docs.google.com/document/d/1vj9z10P2SyQqhKa6f1PSAdsi-cv_H5CUfdYawfKJYSY/mobilebasic

Do NOT rely only on the requirements I list below.

Read the entire document yourself and identify:

- useful concepts I may have missed;
- flaws or oversimplifications in the document;
- ideas that should be adapted rather than copied;
- ideas already implemented in SignalRankAI;
- incomplete implementations already present;
- duplicate implementations that should be consolidated;
- better institutional/quantitative approaches than those proposed;
- additional improvements suggested by current quantitative-finance, ML-validation, trading-system, execution-risk, statistical-testing, and software-engineering best practices.

Treat the Google Doc as research input, **not unquestionable authority**.

The goal is to make SignalRankAI materially more scientifically rigorous, statistically honest, resilient against backtest overfitting, realistic about execution, safer in production, and better at learning which strategies genuinely have persistent edge.

---

# 1. NON-NEGOTIABLE OPERATING RULES

Work against the real current repository.

Do not create a disconnected demo project.

Do not merely produce recommendations, pseudocode, TODO comments, architecture diagrams, reports, or placeholder files.

Implement production-grade code, migrations, tests, configuration, documentation, diagnostics, admin visibility, observability, and integration.

Before changing the architecture:

1. inspect the existing repository;
2. reconstruct the current runtime;
3. inspect the current adaptive-strategy system;
4. inspect all backtesting implementations;
5. inspect current walk-forward validation;
6. inspect ML/model validation;
7. inspect calibration;
8. inspect shadow trading;
9. inspect paper trading;
10. inspect execution simulations;
11. inspect actual/live execution;
12. inspect risk management;
13. inspect position sizing;
14. inspect strategy promotion;
15. inspect strategy quarantine/deactivation;
16. inspect outcome tracking;
17. inspect rejected-signal learning;
18. inspect false-negative and correct-block learning;
19. inspect portfolio-risk controls;
20. inspect kill switches;
21. inspect market-regime logic;
22. inspect strategy statistics;
23. inspect database models;
24. inspect Redis state;
25. inspect worker/scheduler jobs;
26. inspect owner/admin diagnostics;
27. inspect the web dashboard;
28. inspect Telegram diagnostics;
29. inspect current release gates;
30. inspect tests.

Do not assume something is missing just because you have not yet found it.

Search thoroughly.

If functionality already exists and is correct:

**reuse it.**

If functionality exists but is incomplete:

**extend/fix it.**

If there are duplicate competing implementations:

**consolidate them safely.**

Do not regress existing functionality.

---

# 2. CORE PRINCIPLE

The new philosophy for SignalRankAI must be:

```text
Generating ideas is cheap.
Proving an edge is difficult.

Generate many.
Validate aggressively.
Reject most.
Promote very few.
Monitor continuously.
Degrade or halt when evidence deteriorates.
```

Do NOT optimize SignalRank merely for:

- win rate;
- backtest return;
- classification accuracy;
- highest Sharpe;
- prettiest equity curve.

Evaluate strategies using a portfolio of metrics including, where applicable:

- expectancy;
- profit factor;
- Sharpe;
- Sortino;
- Calmar;
- maximum drawdown;
- drawdown duration;
- volatility;
- total R;
- average R;
- median R;
- MAE;
- MFE;
- tail loss;
- risk of ruin;
- turnover;
- fees;
- spread;
- slippage;
- fill rate;
- latency sensitivity;
- calibration;
- Brier score;
- log loss;
- Expected Calibration Error;
- strategy stability;
- parameter stability;
- regime stability;
- out-of-sample robustness;
- live-vs-backtest degradation;
- portfolio correlation/exposure.

---

# 3. REQUIRED RESEARCH PIPELINE

Build or improve the canonical research/promotion lifecycle so strategies effectively pass through:

```text
Research hypothesis
        ↓
Candidate strategy/version
        ↓
Point-in-time dataset
        ↓
Data-quality validation
        ↓
Backtest integrity audit
        ↓
Chronological / purged walk-forward validation
        ↓
Multiple-testing / selection-bias correction
        ↓
Regime robustness validation
        ↓
Execution realism & stress testing
        ↓
Risk survival testing
        ↓
Portfolio interaction testing
        ↓
SHADOW
        ↓
FORWARD_TEST
        ↓
CANARY
        ↓
LIMITED_LIVE
        ↓
PRODUCTION
        ↓
Continuous health / drift monitoring
        ↓
HEALTHY / WATCH / DEGRADED / QUARANTINED / HALTED
```

Adapt this to the existing architecture rather than forcing unnecessary naming changes.

Promotion must be evidence-based and reproducible.

No ML model, strategy, parameter set, or AI-generated candidate may self-promote simply because recent results look good.

---

# 4. RESEARCH HYPOTHESIS REGISTRY

Create or extend a persistent, versioned research hypothesis system.

Every new strategy idea should be capable of recording:

```text
hypothesis_id
strategy_family
strategy_id
parent_hypothesis_id
economic_mechanism
expected_counterparty
reason_edge_should_exist
reason_edge_may_persist
market_inefficiency
asset_scope
asset_class_scope
timeframe_scope
session_scope
expected_regimes
bad_regimes
expected_holding_period
entry_thesis
exit_thesis
invalidation_thesis
known_failure_modes
required_market_data
created_by
created_at
code_commit
status
```

AI-generated hypotheses must not merely say:

```text
RSI < 30 → BUY
```

They should attempt to state an economic or behavioural mechanism.

However, do NOT hallucinate an economic mechanism just to satisfy the schema.

Allow:

```text
mechanism_unproven
```

and treat that appropriately in research ranking.

Pattern-based hypotheses can still be tested, but their weaker prior justification must remain visible.

---

# 5. EXPERIMENT / TRIAL LEDGER

Implement a canonical **Research Experiment Ledger**.

This is critical.

Every meaningful variant tested must be countable.

Examples that can count as separate trials:

- parameter changes;
- indicator-period changes;
- stop changes;
- target changes;
- strategy combinations;
- feature combinations;
- timeframe combinations;
- regime filters;
- asset-specific variants;
- ML hyperparameter experiments;
- Optuna trials;
- alternative entry rules;
- alternative exit rules;
- alternative scoring weights;
- AI-generated variants.

Suggested structure:

```text
experiment_id
hypothesis_id
parent_experiment_id
strategy_id
strategy_version
asset_scope
timeframe_scope
regime_scope
parameter_set
dataset_version
feature_version
label_version
execution_model_version
risk_model_version
code_commit
random_seed
started_at
completed_at
status
counts_as_trial
trial_family
trial_fingerprint
result_summary
```

Prevent duplicate experiments from inflating counts unnecessarily by using deterministic fingerprints where suitable.

But do not falsely reduce the effective number of tests simply because two trials are similar.

Also distinguish:

```text
raw_trial_count
effective_trial_count
```

if dependence-aware multiple-testing methodology is implemented.

Integrate Optuna and all other optimization/search systems with this ledger.

---

# 6. BACKTEST INTEGRITY AUDITOR

Create a deterministic **Backtest Integrity Auditor**.

The Google Doc proposes eight important checks.

Implement them properly and expand them where appropriate.

At minimum validate:

### 6.1 Look-ahead

Ensure a strategy never executes using information unavailable at the decision timestamp.

Do NOT blindly implement `shift(1)` everywhere.

Instead use SignalRank's actual event/time model.

The invariant is:

```text
decision data timestamp <= information available at decision time
execution timestamp > or otherwise realistically executable after decision
```

Check:

- indicators;
- resampling;
- higher-timeframe features;
- swing confirmation;
- labels;
- targets;
- corporate actions;
- economic releases;
- news timestamps;
- model features;
- asynchronous provider data.

### 6.2 Survivorship bias

For relevant asset classes verify:

- delisted equities;
- renamed tickers;
- bankrupt companies;
- expired futures;
- changed index constituents;
- historical market membership;
- crypto delistings;
- contract expirations.

Do not evaluate a historical strategy using only today's surviving universe.

### 6.3 Repainting / future information

Detect or prevent:

- centered moving averages;
- future-confirmed pivots used at the pivot timestamp;
- ZigZag misuse;
- improperly shifted resampling;
- future-filled values;
- bidirectional smoothing;
- full-series normalization;
- global feature scaling;
- future-trained models;
- future corporate actions;
- future regime labels.

### 6.4 Costs

Check that realistic costs are included.

SignalRank is multi-asset, so do NOT use a universal:

```python
fee_bps + slippage_bps
```

Model applicable components such as:

- commission;
- spread;
- slippage;
- funding;
- swap/overnight fees;
- borrow fees;
- exchange fees;
- market impact;
- contract multipliers;
- tick values;
- minimum commissions.

### 6.5 Fill assumptions

Prevent impossible fills.

Consider:

- next-bar execution;
- market-order spread;
- limit-order nonfills;
- gaps;
- stop gaps;
- partial fills;
- queue position where applicable;
- bar high/low ambiguity;
- simultaneous TP/SL touches;
- exchange/broker latency;
- stale quotes;
- minimum size;
- tick size;
- quantity precision.

### 6.6 Parameter fitting

Record:

- number of parameters;
- how they were chosen;
- datasets used;
- whether any validation/test information influenced selection;
- trial count.

### 6.7 Sample / regime coverage

Check whether the sample adequately covers the conditions the strategy claims to handle.

Do not blindly require only:

```text
bull / bear / chop
```

Use SignalRank's richer regime engine.

### 6.8 Data alignment

Validate:

- timezone;
- DST;
- candle-close convention;
- session calendar;
- provider timestamps;
- resampling boundaries;
- higher/lower timeframe synchronization;
- delayed feeds;
- news timestamps;
- corporate-event timestamps.

---

Expand this auditor with any additional institutional-quality checks you identify.

Possible additions:

- label leakage;
- data snooping;
- duplicate observations;
- overlapping labels;
- train/test contamination;
- improper cross-validation;
- universe leakage;
- feature version mismatch;
- dataset revision leakage;
- stale provider substitution;
- market calendar errors;
- unrealistic liquidity;
- insufficient sample;
- execution-capacity assumptions;
- strategy/data mismatch.

Produce structured machine-readable evidence:

```text
audit_id
experiment_id
check_id
status
severity
blocking
reason
evidence
source
dataset_version
strategy_version
code_commit
timestamp
```

Possible statuses:

```text
PASS
WARN
FAIL
NOT_APPLICABLE
UNVERIFIED
```

A generic LLM "critic" may supplement this system, but deterministic checks must remain authoritative where deterministic verification is possible.

---

# 7. MULTIPLE TESTING / SELECTION BIAS

Implement proper correction for repeated experimentation.

The Google Doc suggests Deflated Sharpe Ratio.

Add a production-grade statistical-validation module.

At minimum investigate and implement appropriately:

- Deflated Sharpe Ratio;
- Probability of Backtest Overfitting where appropriate;
- selection-bias correction;
- effective number of trials;
- non-normal return adjustments;
- skew/kurtosis effects;
- sample-size requirements.

Do not simply paste the Google Doc's illustrative function without validating the mathematics and annualization assumptions.

Store:

```text
raw_sharpe
annualization_basis
n_observations
raw_trial_count
effective_trial_count
skew
kurtosis
expected_max_sharpe_from_noise
deflated_sharpe_probability
pbo_or_related_measure
method_version
threshold
pass_fail
```

Make thresholds:

- configurable;
- versioned;
- evidence-backed;
- optionally strategy/asset-class specific.

Do not allow someone to reset trial history by simply renaming a strategy.

Track experiment lineage.

---

# 8. WALK-FORWARD IMPROVEMENTS

SignalRank already has chronological walk-forward infrastructure.

Audit and improve it instead of replacing it unnecessarily.

Ensure:

- chronological training;
- validation/test isolation;
- purge logic where labels overlap;
- embargo where needed;
- point-in-time features;
- no future data;
- reproducible fold definitions;
- correct dataset versions;
- transaction-cost realism.

Add/ensure reporting of:

```text
fold_count
positive_fold_count
positive_fold_ratio
worst_fold_expectancy
worst_fold_profit_factor
worst_fold_sharpe
worst_fold_drawdown
median_fold_expectancy
median_fold_sharpe
mean_fold_sharpe
fold_dispersion
parameter_stability
strategy_stability
regime_stability
cost_stress_stability
sample_size
```

Do not hide unstable behaviour inside aggregate statistics.

Example:

```text
3.8
-0.5
-0.7
-0.2
4.9
```

must be recognized as highly unstable even if the aggregate curve looks attractive.

Add stronger promotion gates using:

- worst folds;
- fraction of positive folds;
- variance across folds;
- parameter sensitivity;
- regime dependency.

---

# 9. REGIME ROBUSTNESS

Integrate research testing with SignalRank's existing market-regime engine.

Do not replace the project's richer regimes with only a 200-period MA classification.

Evaluate strategies across relevant regimes such as:

- strong bullish trend;
- weak bullish trend;
- strong bearish trend;
- weak bearish trend;
- range;
- accumulation;
- distribution;
- breakout;
- failed breakout;
- volatility compression;
- volatility expansion;
- momentum;
- mean-reversion;
- illiquid;
- high-spread;
- risk-on;
- risk-off;
- news/event-driven;
- provider/data uncertainty.

For every strategy determine:

```text
works_well
works_acceptably
weak
disabled
insufficient_evidence
```

per relevant regime.

A strategy specialized for one regime is not automatically invalid.

But the system must know that specialization and prevent it from trading blindly outside that environment.

---

# 10. STRATEGY METRICS

Extend strategy analytics to include, where appropriate:

```text
trade_count
win_rate
loss_rate
break_even_rate
expectancy_r
profit_factor
sharpe
sortino
calmar
max_drawdown
max_drawdown_duration
average_drawdown_duration
average_r
median_r
total_r
volatility
downside_volatility
MAE
MFE
MFE_to_MAE
time_to_first_favourable_move
time_to_first_adverse_move
time_to_target
time_to_stop
turnover
fee_cost
spread_cost
slippage_cost
funding_cost
fill_rate
partial_fill_rate
nonfill_rate
latency
risk_of_ruin
tail_loss
CVaR_or_expected_shortfall
```

Break these down when sample size permits by:

- asset;
- asset class;
- timeframe;
- direction;
- session;
- regime;
- volatility bucket;
- liquidity bucket;
- strategy version;
- feature version;
- model version.

Make uncertainty/sample size obvious.

Do not present statistically weak subgroups as definitive.

---

# 11. DRAWDOWN DURATION

Add drawdown-duration analytics if not already canonical.

Distinguish:

```text
drawdown_depth
drawdown_duration
recovery_duration
```

A strategy with a tolerable 8% drawdown lasting 18 months may be operationally worse than one with a 10% drawdown lasting three weeks.

Expose these metrics in research and owner/admin views.

---

# 12. POSITION SIZING

Audit the Google Doc's position-size example but do NOT use it directly across SignalRank.

SignalRank must size according to instrument specifications.

Support appropriate logic for:

- spot crypto;
- perpetuals;
- futures;
- FX;
- CFDs if supported;
- equities;
- indices;
- commodities;
- metals;
- other supported classes.

Sizing should consider:

```text
account equity
risk budget
entry
stop
stop distance
tick size
tick value
contract multiplier
lot size
quantity precision
minimum quantity
minimum notional
margin requirement
leverage
commission
spread
expected slippage
portfolio exposure
correlation
volatility
liquidity
```

Keep existing conservative Kelly-inspired logic where valid, but audit it.

Never let raw model confidence alone determine dangerous position size.

---

# 13. LOSS-STREAK AND SURVIVAL TESTING

Before promotion, run risk survival tests.

Evaluate:

- losing streaks;
- clustered losses;
- changing volatility;
- gap losses;
- worse-than-expected slippage;
- correlated losses;
- spread widening;
- reduced liquidity;
- partial fills;
- portfolio concentration;
- model degradation.

Use simulation/bootstrapping where statistically appropriate.

Report:

```text
risk_of_ruin
probability_of_X_drawdown
expected_max_drawdown
tail_loss
loss_streak_distribution
capital_survival
```

Do not make claims such as:

```text
12 losses happens once per year
```

without accounting for actual trade frequency and dependence.

---

# 14. EXECUTION STRESS TESTING

Every candidate should be tested under multiple execution conditions.

Examples:

```text
baseline
fees +25%
fees +50%
spread +25%
spread +50%
slippage +25%
slippage +50%
latency increase
partial fills
missed fills
gap execution
liquidity deterioration
```

Strategies whose edge disappears under minor realistic cost changes should receive a robustness penalty or rejection.

---

# 15. LIVE STRATEGY HEALTH

Create or improve persistent approved baselines.

For each promoted strategy/profile record something equivalent to:

```text
baseline_trade_frequency
baseline_win_rate
baseline_expectancy
baseline_profit_factor
baseline_sharpe
baseline_sortino
baseline_calmar
baseline_max_dd
baseline_dd_duration
baseline_MAE
baseline_MFE
baseline_slippage
baseline_spread
baseline_fill_rate
baseline_latency
baseline_calibration
baseline_regime_mix
approved_sample_size
approved_at
approved_version
```

Continuously compare:

- LIVE;
- CANARY;
- LIMITED_LIVE;
- PAPER;
- SHADOW;

with the relevant approved baseline.

Possible states:

```text
HEALTHY
WATCH
DEGRADED
QUARANTINED
HALTED
```

Potential reason codes:

```text
SHARPE_DECAY
EXPECTANCY_DECAY
PROFIT_FACTOR_DECAY
CALMAR_DECAY
DRAWDOWN_EXCEEDED
DRAWDOWN_DURATION_EXCEEDED
LOSS_STREAK_ANOMALY
SLIPPAGE_DEGRADATION
SPREAD_DEGRADATION
FILL_RATE_DEGRADATION
LATENCY_DEGRADATION
CALIBRATION_DECAY
REGIME_MISMATCH
DATA_QUALITY_FAILURE
PROVIDER_FAILURE
OUTCOME_COVERAGE_FAILURE
TRADE_FREQUENCY_DRIFT
FEATURE_DRIFT
MODEL_DRIFT
STRATEGY_DRIFT
```

Do not blindly copy the Google Doc's:

```text
50% Sharpe deterioration
1.5× backtest drawdown
```

as universal constants.

If used, make them defaults subject to proper research, configuration, and strategy-specific thresholds.

---

# 16. PREDEFINED KILL CONDITIONS

Require kill/degradation conditions to be defined before strategy promotion.

Store:

```text
kill_condition_version
conditions
thresholds
approved_by
approved_at
```

Possible automatic responses:

```text
WATCH
REDUCE_WEIGHT
REDUCE_RISK
DISABLE_NEW_ENTRIES
QUARANTINE_STRATEGY
HALT_EXECUTION
OWNER_REVIEW_REQUIRED
```

Never silently reactivate a quarantined strategy.

Require valid recovery evidence.

---

# 17. STRATEGY QUARANTINE AND RECOVERY

Build a governed lifecycle.

Example:

```text
HEALTHY
→ WATCH
→ DEGRADED
→ QUARANTINED
→ RESEARCH_REVIEW
→ SHADOW_REVALIDATION
→ FORWARD_TEST
→ CANARY
→ LIMITED_LIVE
→ PRODUCTION
```

A strategy must not jump directly from failure back into full production.

Keep immutable audit events.

---

# 18. AI / OPENAI ROLE

AI should assist research but must not become an unchecked deterministic trading authority.

Use AI where valuable for:

- hypothesis generation;
- economic-mechanism analysis;
- adversarial critique;
- research summarization;
- post-trade analysis;
- anomaly explanation;
- strategy comparison;
- regime interpretation;
- news interpretation;
- conflicting-evidence analysis;
- owner/admin diagnostics.

But hard gates should remain deterministic wherever possible.

Use schema-constrained structured outputs.

Every AI-assisted research decision should log:

```text
provider
model
model_version
prompt_version
input_fingerprint
output
confidence
timestamp
```

Do not let model output bypass:

- risk;
- data quality;
- multiple testing;
- WFO;
- execution realism;
- portfolio risk;
- promotion gates.

---

# 19. ADVERSARIAL AI CRITIC

Add an optional AI research critic that attempts to reject candidate strategies.

The critic should investigate questions like:

- How could this be leaking?
- What data was unavailable at the actual decision timestamp?
- Could survivorship bias explain this?
- Could selection bias explain it?
- How many variants were tried?
- Is performance concentrated in one fold?
- Is performance concentrated in one asset/regime?
- Does the strategy depend on unrealistic fills?
- Does it disappear after costs?
- Does it disappear after slippage stress?
- Is there insufficient sample size?
- Is the strategy excessively parameter-sensitive?
- Could the observed result be luck?
- What live conditions does the backtest fail to represent?
- What would break this strategy?
- Has the economic mechanism weakened?

The AI critic must return structured findings.

Do not allow the AI critic itself to be the sole promotion gate.

---

# 20. MULTI-ASSET ANNUALIZATION

Audit every annualized metric.

Do NOT use a universal:

```python
periods_per_year = 365
```

SignalRank supports multiple:

- asset classes;
- market calendars;
- timeframes;
- sessions.

Annualization must correctly account for:

```text
instrument market calendar
timeframe
observation interval
24/7 vs session-limited markets
holidays
missing periods
```

Avoid fake precision.

---

# 21. SAME-CANDLE AMBIGUITY

For bar-based simulation, explicitly handle cases where:

```text
TP AND SL
```

are both inside the same candle.

Use a configurable documented conservative rule unless lower-timeframe/order-level data resolves the sequence.

Possible policies must be versioned and stored with the experiment.

Do not silently assume the profitable ordering.

---

# 22. DATA POINT-IN-TIME CORRECTNESS

Ensure all research data is point-in-time safe.

Particularly inspect:

- equities;
- fundamentals;
- earnings;
- macro data;
- index constituents;
- economic releases;
- revised data;
- corporate actions;
- news;
- analyst data;
- alternative data.

If historical revision information is unavailable, record limitations.

---

# 23. MODEL VALIDATION

For ML components, ensure chronological validation.

Never use random splits when temporal leakage may exist.

Use appropriate:

```text
train
validation
test
walk-forward
purging
embargo
```

Track:

```text
dataset_version
feature_version
label_version
model_version
hyperparameters
training_window
validation_window
test_window
code_commit
artifact_hash
```

Maintain Champion/Challenger governance.

---

# 24. CALIBRATION

Continue or improve current calibration.

Evaluate:

```text
Brier score
log loss
ECE
reliability curve
calibration slope/intercept where appropriate
```

Allow calibration to vary by:

- asset class;
- strategy;
- timeframe;
- regime;

only where enough evidence exists.

Do not overfit tiny buckets.

---

# 25. REJECTED SIGNAL ANALYSIS

Preserve and expand SignalRank's ability to learn from rejected signals.

Track why signals were rejected:

```text
ML threshold
AI validation
risk
portfolio
regime
news
duplicate
cooldown
low score
spread
liquidity
data quality
execution eligibility
subscription/user eligibility
```

Evaluate later:

```text
What would have happened?
```

Calculate the incremental value of each filter.

But maintain clear separation between:

- hypothetical;
- shadow;
- paper;
- live-delivered;
- executed;

evidence.

Never mix them into one claimed production win rate.

---

# 26. STRATEGY SELECTION / ENSEMBLES

Use trial-aware, correlation-aware strategy selection.

Ten highly correlated momentum variants must not be interpreted as ten independent confirmations.

Track:

```text
strategy correlation
feature overlap
signal overlap
exposure overlap
regime overlap
```

Penalize redundant evidence.

---

# 27. PORTFOLIO VALIDATION

Do not validate strategies entirely in isolation.

Evaluate interactions such as:

```text
BTC long
ETH long
SOL long
NASDAQ long
```

which may all represent similar risk-on exposure.

Measure:

- correlation;
- beta;
- concentration;
- asset-class exposure;
- currency exposure;
- country exposure;
- sector exposure;
- factor exposure;
- volatility;
- liquidity;
- tail dependence.

Candidate promotion should include portfolio effects where applicable.

---

# 28. CAPACITY / LIQUIDITY

Where relevant, estimate whether historical fills would remain plausible at the intended position size.

Track:

- average volume;
- spread;
- order-book depth where available;
- position relative to volume;
- market impact assumptions;
- expected capacity.

Do not claim scalability beyond available evidence.

---

# 29. STRATEGY DECAY

Distinguish between:

```text
temporary bad luck
market-regime shift
data-quality issue
execution deterioration
structural edge decay
model drift
provider drift
```

Do not automatically retrain or modify production after every bad trade.

New versions must re-enter the validation lifecycle.

---

# 30. AUDITABILITY

Every promoted strategy should be reconstructable.

Given a signal or experiment ID, we should be able to reconstruct:

```text
data used
timestamp
provider
data-quality result
features
feature version
strategy
strategy version
parameters
model
model version
regime
scores
risk decision
portfolio decision
AI decision
execution assumptions
delivery state
actual execution
outcome
learning feedback
```

Use immutable or append-only evidence where appropriate.

---

# 31. DATABASE AND MIGRATIONS

Audit current tables first.

Reuse existing adaptive/research tables where suitable.

Only create new tables where needed.

Potential logical entities include:

```text
research_hypotheses
research_experiments
backtest_integrity_audits
multiple_testing_results
walk_forward_runs
walk_forward_folds
execution_stress_runs
risk_survival_runs
strategy_health_baselines
strategy_health_events
strategy_kill_conditions
strategy_quarantine_events
```

These names are illustrative.

Follow the repository's conventions.

Create proper migrations.

Ensure:

- backwards compatibility where required;
- indexes;
- foreign keys;
- uniqueness constraints;
- idempotency;
- retention strategy;
- staging/production safety;
- rollback/recovery documentation.

---

# 32. OWNER/ADMIN UI

Expose useful research evidence in the web application.

Create or improve views for:

### Strategy Research

Show:

```text
hypothesis
experiment count
latest version
trial history
raw metrics
adjusted metrics
DSR
WFO
regime performance
execution stress
risk survival
promotion state
```

### Strategy Health

Show:

```text
health status
baseline
live statistics
drift
alerts
quarantine reason
recovery state
```

### Backtest Integrity

Show:

```text
lookahead
survivorship
repainting
cost model
fill model
parameter fitting
regime coverage
alignment
other checks
```

### Promotion Evidence

Show:

```text
what gates passed
what gates failed
evidence timestamps
dataset/model/code versions
```

Do not let admin UI mutate production evidence silently.

All overrides must be audited.

---

# 33. TELEGRAM / OWNER DIAGNOSTICS

Where consistent with current product architecture, expose concise owner diagnostics.

Examples:

```text
/research
/strategy_health
/wfo
/backtest_audit
```

Do not spam ordinary users with internal research data.

Preserve role permissions.

Website and Telegram should derive from the same canonical backend truth.

---

# 34. OBSERVABILITY

Add metrics/logging/tracing for:

```text
experiments created
experiments completed
experiments rejected
integrity failures
multiple-testing failures
WFO failures
shadow promotions
quarantines
health alerts
strategy reactivations
research job failures
```

Owner diagnostics should distinguish:

```text
no edge
insufficient evidence
research job broken
market data unavailable
validation failure
strategy intentionally quarantined
```

---

# 35. TESTING

Add comprehensive tests.

At minimum:

### Look-ahead tests

Create intentionally leaky strategies and ensure they fail.

### Resampling tests

Ensure higher-timeframe bars aren't visible before close.

### Swing/pivot tests

Prevent future-confirmed pivot leakage.

### Feature scaling tests

Ensure scalers fit training data only.

### WFO tests

Ensure future rows cannot enter training.

### Purge/embargo tests

Ensure overlapping labels do not leak.

### Multiple-testing tests

Ensure trial count changes adjusted significance.

### Experiment lineage tests

Renaming a strategy must not erase historical experimentation.

### Cost tests

Ensure turnover incurs costs correctly.

### Fill tests

Ensure impossible limit fills are rejected.

### Same-bar ambiguity tests

Ensure conservative documented behaviour.

### Annualization tests

Crypto daily, crypto intraday, FX, equity sessions etc.

### Drawdown-duration tests

Verify underwater duration.

### Health-monitor tests

Trigger synthetic degradation and verify state changes.

### Quarantine tests

Verify degraded strategies cannot silently resume.

### Database tests

Migration/up/down or approved rollback workflow.

### API tests

Owner/admin endpoints.

### Security/RBAC tests

Research controls should not be available to ordinary users.

### Regression tests

Existing signal generation must remain correct.

---

# 36. SECURITY

Do not allow:

- client/user access to internal strategy IP without permission;
- ordinary users to manipulate strategy promotion;
- unaudited manual promotion;
- arbitrary model-artifact upload;
- unsafe deserialization;
- secrets in research records;
- user input to execute research code;
- arbitrary code execution via strategy definitions;
- SQL injection;
- unsafe pickle loading;
- forged experiment evidence.

Treat model and strategy artifacts as security-sensitive.

---

# 37. PERFORMANCE

Do not make production signal generation depend synchronously on heavy backtesting or research.

Research workloads belong in suitable workers/jobs.

Use:

- queueing;
- distributed locks;
- idempotency;
- timeouts;
- retries;
- bounded concurrency;
- resource limits.

A research failure must not crash the live signal engine.

---

# 38. GOOGLE DOCUMENT QUALITY REVIEW

Do not simply reproduce the linked guide.

Audit its assumptions.

Examples already worth questioning:

1. `periods_per_year = 365` is not universal.
2. `.iloc` windows named `train_days` are actually row-count windows unless frequency is guaranteed.
3. `turnover * (fee + slippage)` is simplistic for SignalRank.
4. `capital * risk / stop_distance` does not universally size all instrument types.
5. Sharpe >2 or >3 is not proof of leakage; it is a reason for deeper investigation.
6. Losing-streak frequency depends on the number of trades and dependence structure.
7. A fixed 180/60 walk-forward window is not universally optimal.
8. A 200-MA bull/bear/chop regime is too simple for SignalRank.
9. Fixed 1% trade risk is an example, not a universal production requirement.
10. Fixed 50% Sharpe-decay / 1.5× drawdown halt thresholds should not automatically become universal rules.

Find any other assumptions yourself.

Improve them.

---

# 39. ADD YOUR OWN IMPROVEMENTS

After reading:

- the linked Google Doc;
- current SignalRank code;
- current SignalRank specifications;
- tests;
- release gates;
- research literature already referenced in the repository;

identify any additional high-value improvements that I have not explicitly requested.

Potential areas to consider:

- White's Reality Check;
- Hansen's SPA test;
- Probability of Backtest Overfitting;
- combinatorial purged cross-validation where appropriate;
- bootstrap confidence intervals;
- block bootstrap for dependent returns;
- false-discovery-rate control;
- parameter sensitivity surfaces;
- stability selection;
- nested temporal validation;
- Bayesian strategy comparison;
- model uncertainty;
- conformal methods where appropriate;
- stress/scenario testing;
- Monte Carlo trade-sequence reshuffling;
- serial correlation;
- heteroskedasticity;
- autocorrelation-adjusted Sharpe;
- downside/tail metrics;
- expected shortfall;
- market-capacity estimation;
- data provenance;
- immutable dataset snapshots;
- reproducibility;
- deterministic random seeds;
- research compute quotas;
- model drift;
- concept drift;
- strategy crowding;
- capacity decay;
- feature leakage detection;
- cross-asset leakage;
- stale feature detection;
- experiment lineage graphs.

Do not add complexity merely because something sounds sophisticated.

Only integrate techniques appropriate to SignalRank and its available evidence.

---

# 40. DO NOT FABRICATE PERFORMANCE

Absolutely do not claim:

```text
70% win rate
profitable
production-ready
institutional-grade
live-safe
proven edge
```

unless supported by actual evidence.

Tests passing do not prove profitability.

Backtests do not prove live profitability.

Shadow does not equal live.

Paper does not equal live.

Canary does not equal mature production.

Maintain these evidence classes separately.

---

# 41. CURRENT PROJECT SAFETY

Preserve all existing SignalRank functionality, including:

- multi-asset support;
- crypto;
- forex;
- indices;
- equities/stocks;
- commodities;
- existing strategy library;
- market-regime engine;
- ML validation;
- OpenAI/AI integration;
- news;
- shadow tracking;
- false-negative analysis;
- correct-block analysis;
- paper trading;
- risk management;
- Telegram;
- website;
- subscriptions;
- user eligibility;
- execution;
- owner diagnostics;
- Redis;
- PostgreSQL;
- Railway deployment;
- migrations;
- kill switches;
- audit systems.

Do not weaken thresholds simply to increase signal frequency.

A correct:

```text
NO TRADE
```

is better than a low-quality forced signal.

---

# 42. DELIVERABLES

When implementation is complete, provide:

## A. Repository audit

Explain:

```text
already existed
partially existed
missing
duplicated
incorrect
replaced/consolidated
```

## B. Google Doc extraction

List every substantive concept found in the Google Doc and classify it as:

```text
IMPLEMENTED
IMPROVED
ALREADY_PRESENT
REJECTED_WITH_REASON
DEFERRED_WITH_REASON
NOT_APPLICABLE
```

Do not omit ideas simply because they seemed minor.

## C. Implementation report

List every changed file.

## D. Database report

List migrations and any required commands.

## E. Environment variables

List every new variable.

Use:

```text
VARIABLE=
```

without secret values.

Explain what each controls.

## F. Tests

List tests added and actual results.

## G. Research-validation status

Report:

```text
hypothesis registry
experiment ledger
integrity auditor
multiple testing
WFO
regime robustness
execution stress
risk survival
health monitoring
quarantine
UI
Telegram/admin diagnostics
```

## H. Evidence ledger

For every requirement use:

```text
IMPLEMENTED
VERIFIED
BLOCKED_EXTERNAL
DEFERRED
NOT_APPLICABLE
```

Do not mark something verified merely because code exists.

## I. Remaining blockers

Explicitly list anything requiring:

- live market sessions;
- broker credentials;
- production data;
- extended soak;
- real fills;
- owner approval;
- external services;
- longer sample collection.

## J. Git details

Return:

```text
branch
final commit SHA
PR
migration head
tests
deployment notes
```

---

# 43. COMPLETION STANDARD

Do not stop after scaffolding.

Continue until every requirement from:

1. this prompt;
2. the Google Doc;
3. relevant existing SignalRank specifications;
4. newly discovered high-value gaps;

has been:

```text
implemented,
verified,
or explicitly classified with a truthful blocker/reason.
```

Before declaring completion, perform another repository-wide audit.

Ask:

```text
What did we miss?
What remains disconnected?
What still uses fake or optimistic assumptions?
What validation can still leak future information?
What allows overfitting?
What research evidence can be reset or manipulated?
What production strategy can remain active after its edge deteriorates?
What failure mode still lacks an alert?
What owner/admin view still reports misleading statistics?
What existing implementation duplicates the new one?
What can still produce an impossible backtest fill?
```

Fix every material issue you can verify.

Then perform a second adversarial review of the completed implementation.

Do not declare the system "perfect."

Instead provide evidence and clearly identify anything that still requires real-world validation.

The end goal is not to produce more strategies.

The end goal is to make SignalRankAI exceptionally good at determining:

```text
which strategies deserve to exist,
which deserve promotion,
which should remain experimental,
which should be quarantined,
and when a previously valid strategy should stop trading.
```