# SignalRankAI v1.1.1 — Adaptive Operational Hotfix

This release is additive to v1.1.0 and all pre-existing strategy groups.

## Fixed

- Corrected the 0025 adaptive migration index to use `started_at`.
- Added migration 0026 for schema compatibility, decision-log timestamp repair,
  and indexed short signal-reference lookup.
- Monitor callbacks now resolve full or shortened signal IDs and verify the
  signal was Telegram-confirmed for the requesting user.
- Signal keyboards prefer the canonical full UUID from the persisted payload.
- Resend batches rotate across users instead of permanently starving users after
  the first configured page.
- Unified stale and final-send entry-drift validation into one bounded,
  volatility/risk-aware threshold.
- Added canonical asset classification to prevent FX and macro instruments from
  falling through to stock policy.
- Added macro/yield timeframe policy where daily data is authoritative.
- Normalised nested Bollinger width contracts.
- Fixed WebSocket circuit cooldown to sleep the full configured interval.
- Added TradingView caching, negative caching, and a rate-limit circuit.
- Deferred decision annotations are retained in a bounded retry queue rather
  than immediately discarded when the background DB lane is unavailable.
