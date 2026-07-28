# Adaptive Strategy Intelligence Engine v1.1.0

## Implemented runtime path

Market data → candle-quality validation → confirmed-pivot/feature context → modular strategy evidence → approved-profile bounded weighting → existing scoring, ML, Gemini, news, risk, deduplication and delivery gates → signal evidence/sequence-reference persistence → outcomes → analytics-only candidate profile generation.

## Components

ICT/SMC, price action, supply and demand, Fibonacci, harmonic patterns, probabilistic Elliott Wave, genuine-data-only order flow, conservative Wyckoff classification, and contextual indicator evidence are implemented as separate typed deterministic components.

## Safety properties

- Research/shadow profiles have no live weighting effect.
- Runtime multipliers are bounded and cannot override deterministic risk gates.
- Order-flow evidence is marked unavailable when genuine bid/ask or delta data is absent.
- Pivots exclude the final confirmation window to prevent look-ahead leakage.
- Optimisation produces SHADOW candidates only. Promotion to CANARY/LIMITED_LIVE requires independent gates and human approval.
- Database sessions are not held across provider, Telegram, Gemini, Redis or broker calls.
- Full candle arrays are not duplicated inside signal rows; signals persist canonical sequence hashes and summaries.

## Honest limitations

This release is the production foundation and live runtime integration. Reliable profile promotion still requires sufficient historical candles, completed outcomes, chronological walk-forward runs, shadow/forward evidence, execution-cost calibration, and owner approval. No profitability or minimum win rate is claimed.
