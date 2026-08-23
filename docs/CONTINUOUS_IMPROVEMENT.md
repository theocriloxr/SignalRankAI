# Continuous Improvement

SignalRankAI's continuous-improvement loop is evidence-driven and recommendation-only. It does not autonomously modify source, deploy releases, change risk limits, activate payments, or enable execution.

## Workflow

1. Aggregate proof-backed signal, delivery, outcome, rejection, provider, and calibration metrics.
2. Remove user identifiers, contact details, payment data, credentials, and tokens.
3. Hash the canonical research snapshot for lineage.
4. Produce a deterministic local review.
5. Optionally request an aggregate-only OpenAI Responses API review when explicitly enabled and configured.
6. Normalize suggestions into evidence-backed recommendations requiring owner approval.
7. Move approved experiments sequentially through backtest, walk-forward, shadow, paper, staging, and production-eligibility evidence states.
8. Hand code recommendations to Codex as reviewable engineering tasks with production mutation explicitly unauthorized.

Run a local review without external API calls:

```bash
python -m tools.continuous_improvement_review --days 7
```

Opt in to an external aggregate review only after configuring the OpenAI key and budget controls:

```bash
python -m tools.continuous_improvement_review --days 7 --external-openai
```

JSON and Markdown evidence is written under `artifacts/continuous-improvement/`. The output includes the code SHA, period, dataset hash, incidents, recommendations, and external-review status.

## Promotion safety

Experiments cannot skip states. Every transition requires an evidence ID. Production eligibility additionally requires owner approval plus tests, walk-forward, shadow, paper, staging-soak, and rollback evidence. Eligibility is not activation: the independent release guard remains authoritative.

## Privacy and cost

Only aggregate research context may leave the application boundary. External review is disabled by default. Raw candles, users, Telegram IDs, signal IDs, emails, payment records, API credentials, and broker credentials are excluded. Deterministic aggregation runs before any model request to constrain token and provider cost.
