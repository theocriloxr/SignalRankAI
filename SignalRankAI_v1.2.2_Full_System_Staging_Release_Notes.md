# SignalRankAI v1.2.2 — Full-System Staging Test Mode

This hotfix preserves the v1.2.1 import and paper-session repairs and adds an explicit integration-test profile that enables all major feature paths in staging.

## Behaviour

- Requires `FULL_SYSTEM_STAGING_TEST_MODE=1` and the exact acknowledgement token.
- Enables auto execution, copy trading, Bybit execution, payments, payout readiness, free-tier distribution, WebSockets, rich-message canary, adaptive shadow candidates, and automatic paper execution.
- Restricts Telegram delivery to `FULL_SYSTEM_TEST_USER_IDS`.
- Forces Bybit testnet and Paystack public test mode.
- Blocks live MT5 accounts with a second execution-gate permission even when `REAL_EXECUTION_ENABLED=1`; use a MetaApi demo account to exercise the real broker pipeline.
- Fails closed when the acknowledgement is missing or invalid.

`REAL_PAYOUTS_ENABLED=1` exercises the current payout-readiness feature. The repository does not contain a completed Paystack Transfer disbursement adapter, so this flag does not by itself prove external payout execution.
