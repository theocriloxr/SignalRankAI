# SignalRankAI v1.2.3 Certification Report

Date: 2026-07-29
Scope: log-driven adaptive, signal-pipeline, paper-trading, and full-system staging hotfix

## Verified locally

- Python compilation: PASS
- Adaptive legacy import compatibility: PASS for 9 component modules
- v1.2.3 runtime fingerprint verifier: PASS
- Alembic schema audit: PASS, 27 revisions, sole head `0027_launch_paper_trading`
- Production readiness: PASS, 8/8 checks
- DB session API audit: PASS, 0 legacy call sites
- Architecture smoke audit: PASS
- Focused regression suite: 59 passed, 3 dependency-bound tests deselected

The three deselected tests import APScheduler or python-telegram-bot. Both dependencies are declared in `requirements.txt` and were present in the Railway runtime logs, but are not installed in this local certification container.

## Log-derived defects addressed

- Stale/hybrid runtime identification
- Divergent acknowledgement validation
- Missing `engine.adaptive.fibonacci` and sibling compatibility paths
- Adaptive candle/evaluation startup failure
- Paper worker DB admission exception storm
- Waitlist DB admission error noise
- Regime detector receiving a timeframe dictionary instead of candles
- Ultra-quality gate executing before risk levels and context
- Ultra-quality target, direction, regime, session, and confidence normalisation
- Missing Paystack public-key field in the staging template
- Proxy validation enabled without a provider URL

## Not yet live-certified

The following require a new Railway deployment and runtime evidence:

- Boot banner must show v1.2.3 and the release fingerprint.
- Full-system staging acknowledgement must be valid in the main process.
- Adaptive bot setup and candle capture must start without import errors.
- Paper worker must complete cycles without exception tracebacks.
- At least one high-scoring signal must pass the corrected structural/quality sequence and be stored or receive a real, post-construction rejection reason.
- Paystack test, Bybit testnet, MT5 demo, copy-trading, and payout workflow proof requires valid sandbox credentials and controlled test actions.

Status: code-complete and locally verified; Railway live certification pending redeployment logs.
