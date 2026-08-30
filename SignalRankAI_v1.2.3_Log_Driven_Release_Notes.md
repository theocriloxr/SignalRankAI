# SignalRankAI v1.2.3 — Log-Driven Full-System Staging Hotfix

Date: 2026-07-29

## Why this release exists

The 16,216-line Railway log from the v1.2.2 staging attempt exposed a hybrid/stale deployment and three runtime blockers:

1. The boot banner still identified the process as v1.2.0 and startup safety rejected the full-system acknowledgement even though the diagnostics subprocess later accepted it.
2. `engine.adaptive.fibonacci` was missing, preventing Telegram bot setup, adaptive candle capture, and adaptive strategy evaluation.
3. Paper trading treated expected database admission deferrals as fatal cycle failures.
4. High-scoring candidates were repeatedly rejected by the ultra-quality gate before stop-loss, take-profit, regime, and session data were populated, producing artificial `R:R 0.00` rejections and zero stored signals.

## Corrections

- Added compatibility modules for every adaptive component expected by older import paths.
- Added a code-owned v1.2.3 runtime version and release fingerprint; stale Railway `APP_VERSION` is shown separately as `configured_version`.
- Unified full-system acknowledgement validation and accepts a value accidentally wrapped in matching quotes by a deployment UI.
- Added explicit startup-safety telemetry showing requested, acknowledgement-valid, enabled, and environment values.
- Regime detection now receives a real candle sequence selected from the available timeframe data.
- Ultra-quality filtering now runs after executable entry, stop, targets, regime, ADX, volume, volatility, and session context are populated.
- Ultra-quality parsing now supports `stop_loss`, scalar/list/dict targets, BUY/SELL direction aliases, uppercase regimes, session aliases, and percentage confidence values.
- Paper delivery and mark-to-market phases are isolated; expected DB admission deferrals are throttled informational events rather than repeated exception tracebacks.
- Added configurable paper DB priority and timeout values for full-system staging tests.
- Waitlist DB admission deferrals are also logged as expected deferrals rather than application errors.
- Proxy validation defaults off when no provider URL is supplied.
- Added a flat/root-level deployment ZIP to prevent accidental nested or partial overlays.

## Test-mode boundaries

Every major workflow may be enabled in staging, but external money boundaries remain:

- MT5 live accounts blocked: `MT5_ALLOW_LIVE_ACCOUNTS=0`
- Bybit forced to testnet: `BYBIT_TESTNET=1`
- Paystack requires `sk_test_...` and `pk_test_...`
- Telegram delivery restricted to `FULL_SYSTEM_TEST_USER_IDS`

## Database

No new migration. Expected head remains `0027_launch_paper_trading`.
