# Continuous Improvement

SignalRankAI's continuous-improvement loop is evidence-driven and recommendation-only. It does not autonomously modify source, deploy releases, change risk limits, activate payments, or enable execution.

## Workflow

1. Record the complete observable decision surface: every market scan, no-setup observation, issued candidate, rejected/skipped candidate, pending/ambiguous shadow result, regime, score bucket, asset class, timeframe, and strategy.
2. Aggregate proof-backed signal, delivery, outcome, rejection, provider, and calibration metrics. Issued canonical outcomes have weight `1.0`; counterfactual rejected/skipped shadow outcomes have weight `0.60`. Pending, ambiguous, and no-data rows measure coverage but cannot become training targets.
3. Remove user identifiers, contact details, payment data, credentials, and tokens.
4. Fit a Beta-smoothed monotonic score mapping and validate it on the newest chronological 20% holdout. Store the result as a shadow profile with Brier and calibration-error evidence.
5. Hash the canonical research snapshot for lineage and produce a deterministic local review.
6. Optionally request independent aggregate-only OpenAI Responses API and Gemini reviews when explicitly enabled and configured.
7. Calculate source/decision/asset-class/timeframe/strategy/regime Wilson intervals. This detects both weak issued segments and false-negative concentrations among rejected setups.
8. Normalize suggestions into evidence-backed recommendations requiring owner approval.
9. Move approved experiments sequentially through backtest, walk-forward, shadow, paper, staging, and production-eligibility evidence states.
10. Hand eligible code recommendations to a dual-provider refactor workflow: OpenAI proposes exact bounded replacements, local guards validate paths and syntax, Gemini independently reviews the exact patch, the full repository certification runs, and only then is a draft PR opened.

## Scoring and calibration

The heuristic score is an auditable normalized weighted average. Confidence, ML probability, R/R quality, volatility, confluence, regime fit, and candle evidence each appear once; there are no multiplicative ML, regime, or exceptional-R/R boosts. `score_raw`, `score_heuristic`, `score_components`, and `score_calibration_method` preserve lineage.

`SCORE_EMPIRICAL_CALIBRATION_SHADOW_ENABLED=1` records the learned probability as `score_empirical_shadow` without changing delivery thresholds or the live score. `SCORE_EMPIRICAL_CALIBRATION_ENABLED=1` still cannot activate a sparse or failed profile: the profile must meet the configured sample and chronological holdout minimums and avoid worsening Brier score or calibration error. Keep live activation off until staging forward tests also prove expectancy, drawdown, loss-streak, asset coverage, and data-quality gates.

This learns the full *observable* market surface, not an unknowable idealized market. A no-setup scan has no entry/stop/target and therefore contributes coverage/regime evidence, not a fabricated win/loss label. A rejected candidate with a complete trade thesis can be shadow-tracked and becomes a lower-weight counterfactual label after its evaluation window closes.

Run a local review without external API calls:

```bash
python -m tools.continuous_improvement_review --days 7
```

Opt in to an external aggregate review only after configuring the OpenAI key and budget controls:

```bash
python -m tools.continuous_improvement_review --days 7 --external-openai
```

Run both independent reviewers:

```bash
python -m tools.continuous_improvement_review --days 7 --external-openai --external-gemini
```

JSON and Markdown evidence is written under `artifacts/continuous-improvement/`. The output includes the code SHA, period, dataset hash, incidents, recommendations, and external-review status.

The analytics runtime role schedules this same implementation weekly when `CONTINUOUS_IMPROVEMENT_REVIEW_ENABLED=1`. The scheduler uses a durable last-run cursor, starts after the configured delay, and never runs in the front-door or engine ownership lanes. `/codex_audit` remains the owner/admin interactive evidence-review surface.

## Draft PR refactoring

This connects the deployed learner to the repository without granting it merge or deployment authority. The runtime may emit a minimal `repository_dispatch` event for one eligible low/medium-risk code recommendation. `.github/workflows/continuous-refactor.yml` creates an isolated branch, generates a bounded patch, runs compile and full certification, and opens a **draft** PR. Failed OpenAI output, missing Gemini review, disallowed paths, ambiguous replacements, syntax errors, test failures, or an empty patch all stop the workflow.

Required GitHub configuration:

- Repository Actions variable `CONTINUOUS_REFACTOR_ENABLED=true`.
- Actions secrets `OPENAI_API_KEY` and `GEMINI_API_KEY`.
- Railway analytics variables `CONTINUOUS_REFACTOR_DISPATCH_ENABLED=1`, `CONTINUOUS_REFACTOR_GITHUB_REPOSITORY=theocriloxr/SignalRankAI`, and a fine-grained `CONTINUOUS_REFACTOR_GITHUB_TOKEN` that can dispatch repository events.
- Keep the default path allowlist until several draft PRs are reviewed successfully. Expanding it to trading-engine paths is a separate owner decision.

This ChatGPT conversation is not a persistent API endpoint. `OPENAI_API_KEY` connects the system to the OpenAI Responses API; future draft PRs can then be reviewed here or by Codex before merge.

## Promotion safety

Experiments cannot skip states. Every transition requires an evidence ID. Production eligibility additionally requires owner approval plus tests, walk-forward, shadow, paper, staging-soak, and rollback evidence. Eligibility is not activation: the independent release guard remains authoritative.

The legacy `worker.ai_feedback.apply_recommendation` and `AutoOptimizerRunner.apply_recommended_sl` names are retained for compatibility, but both record proposals only. They cannot update `ENGINE_BASE_THRESHOLD`, `ML_PROB_THRESHOLD`, `STOP_LOSS_PCT`, or another live runtime setting.

## Privacy and cost

Only aggregate research context may leave the application boundary during performance review. External review is disabled by default. Raw candles, users, Telegram IDs, signal IDs, emails, payment records, API credentials, and broker credentials are excluded. Deterministic aggregation runs before any model request to constrain token and provider cost.

The separate refactor workflow can share only explicitly allowlisted source files and is disabled by default. It never reads `.env`, migrations, authentication, payments, broker execution, or deployment workflows under the default guards.
