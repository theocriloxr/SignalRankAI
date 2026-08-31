# Continuous Improvement

SignalRankAI's continuous-improvement loop is evidence-driven and recommendation-only. It does not autonomously modify source, deploy releases, change risk limits, activate payments, or enable execution.

## Workflow

1. Aggregate proof-backed signal, delivery, outcome, rejection, provider, and calibration metrics.
2. Remove user identifiers, contact details, payment data, credentials, and tokens.
3. Hash the canonical research snapshot for lineage.
4. Produce a deterministic local review.
5. Optionally request independent aggregate-only OpenAI Responses API and Gemini reviews when explicitly enabled and configured.
6. Calculate per-asset-class/timeframe/strategy Wilson intervals and expectancy; weak or strong segments become shadow-only experiment proposals after the minimum sample.
7. Normalize suggestions into evidence-backed recommendations requiring owner approval.
8. Move approved experiments sequentially through backtest, walk-forward, shadow, paper, staging, and production-eligibility evidence states.
9. Hand eligible code recommendations to a dual-provider refactor workflow: OpenAI proposes exact bounded replacements, local guards validate paths and syntax, Gemini independently reviews the exact patch, the full repository certification runs, and only then is a draft PR opened.

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
