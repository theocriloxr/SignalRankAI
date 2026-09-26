# Living User Experience Register

Last updated: 2026-09-26
Owner: Product/Engineering

This register separates **copy/interaction quality** from **external end-to-end proof**.
Premium copy is considered verified only when active runtime surfaces use the
canonical capability-aware contract and regression tests block stale claims.
Telegram Bot API callback/E2E proof remains tracked separately under LTD-003.

| Surface | Files | Clarity | Consistency | Accessibility | Professionalism | Test Coverage | Known Limitations | Planned Improvements | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/start` onboarding | `signalrank_telegram/ux_copy.py`, `commands.py`, `user_commands.py` | Good | Good | Partial | Good | `tests/test_premium_ux_contract.py` | External Bot API rendering remains sandbox-dependent | Keep snapshot/copy contract current with product changes | Verified |
| `/help`, FAQ, support | `signalrank_telegram/ux_copy.py`, `commands.py`, `user_commands.py` | Good | Good | Partial | Good | Premium UX + command contracts | Telegram client rendering/E2E remains external | Sandbox E2E under LTD-003 | Verified |
| Signal cards and evidence | `signalrank_telegram/formatter.py`, `tier_gated_formatter.py`, web signal detail | Good | Good | Partial | Good | Formatter, lifecycle, premium UX contracts | Visual rendering varies by Telegram/client viewport | Continue visual regression review | Verified |
| Inline keyboards | `commands.py`, `bot.py`, callback registry | Good | Good | Partial | Good | Callback/registry/source contracts | Full live Bot API callback journey is external-proof pending | Execute sandbox workflow checklist under LTD-003 | Verified locally / external proof pending |
| Plans, checkout, renewal and refund review | `signalrank_telegram/ux_copy.py`, `web/platform_app/*`, `web/app.py`, `payments/*` | Good | Good | Partial | Good | Premium UX, payment/catalog, webhook/idempotency tests | Paystack live-provider proof remains external | Provider-certified staging checkout before production activation | Verified locally / external proof pending |
| Connected-account / execution UX | `web/platform_app/*`, broker/account policy surfaces | Good | Good | Partial | Good | Premium UX, broker safety, BOLA/account-policy tests | Provider execution remains separately certified | Preserve account/provider/risk/reconciliation language | Verified |
| Reports / quality / admin | Telegram owner/admin commands and web evidence surfaces | Good | Good | Partial | Good | Selected governance, observability and command tests | Operator ergonomics remain iterative, not a public-copy blocker | Continue operational UX maintenance | Maintained |
| Error messages | `command_resilience.py`, `ux_copy.py`, web toasts/API errors | Good | Good | Partial | Good | Premium UX, secret-redaction and API tests | External provider text may still vary | Normalize newly introduced provider errors at adapter boundary | Verified |
