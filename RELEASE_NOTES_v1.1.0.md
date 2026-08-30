# SignalRankAI v1.1.0 — Adaptive Strategy Intelligence Foundation

Release date: 2026-07-28
Baseline: v1.0.8 Operational Gaps Hotfix
Migration head: `0025_adaptive_strategy`

## Added

- Runtime-connected adaptive asset-specific strategy evaluation.
- Structured components for ICT/SMC, price action, supply/demand, Fibonacci, harmonics, probabilistic Elliott Wave, genuine-data-only order flow, Wyckoff and indicator evidence.
- Candle quality checks and bounded asynchronous canonical candle capture.
- Stable pre-signal sequence references without duplicating full candles in signal rows.
- Persistent strategy specifications, asset profiles, evidence, sequences, dataset versions, feature versions, WFO runs, optimisation runs, promotion events and drift events.
- Chronological purged walk-forward validation with cost modelling and regression tests against future-row leakage.
- Stable candidate fingerprints to suppress duplicate challenger versions.
- SHADOW-only candidate creation and bounded runtime weighting.
- Staged lifecycle: SHADOW → FORWARD_TEST → CANARY → LIMITED_LIVE.
- Telegram owner controls for status, pause, resume, promotion, suspension and rollback.
- Confirmed-live drift monitoring with automatic suspension and rollback.
- Architecture, data dictionary, threat analysis and operations runbook.

## Safety

- Research and SHADOW profiles have neutral runtime influence.
- Automatic live promotion is disabled.
- Missing calibration blocks promotion.
- Existing deterministic risk, portfolio, news, delivery, cooldown, eligibility and execution controls remain authoritative.
- Order-flow evidence is never fabricated from candle volume.
- Real-money execution, copy trading, public payments and payouts are not enabled by this release.

## Validation

- Repository compilation: 714 tracked Python files, zero failures.
- Schema audit: 25 revisions, sole head `0025_adaptive_strategy`.
- DB session audit: zero legacy call sites.
- Governance validation: 24 documents passed.
- Production readiness checks: 8/8 passed.
- Architecture smoke: passed.
- Secret scan: zero findings.
- Adaptive/focused release suite: 48 passed.
- Dependency-independent repository suite: 344 passed, 1 skipped.
- Full collection discovered 800 tests; seven collection modules were blocked locally because `python-telegram-bot` and/or `APScheduler` are not installed in the certification container. Both are declared in `requirements.txt` and must be installed by Railway before deployment.

## Limitations

This release implements the integrated production foundation and controlled learning lifecycle. It does not claim that every named discretionary framework has already achieved asset-specific statistical reliability. Promotion remains blocked until sufficient sequence coverage, chronological WFO, confidence calibration, shadow/forward evidence and live canary evidence exist.
