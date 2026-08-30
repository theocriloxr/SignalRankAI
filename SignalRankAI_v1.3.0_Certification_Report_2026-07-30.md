# SignalRankAI v1.3.0 Certification Report

## Scope

This report certifies the source archive and static/isolated tests available in the local certification environment. It does not claim that external Railway, Telegram, Redis, PostgreSQL, Paystack, Gemini, market-data, MT5, or Bybit services have been exercised from this container.

## Log-grounded incident findings

- Deployment identity: v1.2.9 running in Railway staging mode.
- Outcome persistence failures: 514 occurrences of PostgreSQL `InvalidColumnReferenceError` caused by an unmatched `ON CONFLICT (signal_id)` target.
- Portfolio blocks: 510 occurrences at the five-trade global limit.
- Candidate generation remained active: 285 logged strategy-generation events.
- Observed nonzero stored or dispatched batches: zero.
- Resend audience remained restricted to two matched users out of five.
- TradingView rate-limit exhaustion and WTI ghost-instrument rejection were secondary provider defects.

## Implemented controls

- Active migration head `0028_outcome_projection_guard`.
- Duplicate outcome reconciliation and notification-FK preservation.
- Unique outcome projection index, including repair of a same-name non-unique drifted index.
- Advisory-lock plus row-lock update/insert writer.
- Runtime and deployment diagnostic checks for outcome duplicates and unique guard.
- Production-only readiness gate and automatic staging-state removal.
- Readiness rejection for placeholder credentials, shared Redis roles, invalid public Paystack key mode, and missing MetaAPI token when demo execution is enabled.
- Global delivery eligibility in production.
- TradingView disabled in production.
- Correct commodity/index/FX Yahoo mappings.
- Commodity-aware portfolio exposure classification.
- Portfolio exposure and all real-money paths remain fail-closed.

## Test evidence

- Focused production, outcome, migration, provider, and v1.2.x compatibility suite: 126 passed.
- Broad dependency-free repository suite: 480 passed, 1 skipped.
- Production readiness checks: 9/9 passed.
- Schema audit: passed; 28 revisions; sole head `0028_outcome_projection_guard`.
- Architecture smoke: passed.
- Legacy DB session API call sites: 0.
- Secret scan findings: 0.
- v1.2.5, v1.2.6, v1.2.7, v1.2.8, v1.2.9, and v1.3.0 compatibility verifiers: passed.

## Environment limitation

Seven full-suite collection modules require `python-telegram-bot` and/or APScheduler. Both dependencies are declared in `requirements.txt`, but the local certification package index contained no installable distributions. Those modules therefore require the Railway production image for runtime proof.

## Certification conclusion

The source-level cause of the no-signal incident is repaired and guarded at schema, runtime writer, diagnostics, and readiness layers. The archive is suitable for a controlled production deployment with manual/paper signal delivery. Production success still requires the exact Railway environment and runtime evidence listed in the launch checklist. No claim of globally certified live-money execution or universal payment availability is made.
