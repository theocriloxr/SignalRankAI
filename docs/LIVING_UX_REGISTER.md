# Living User Experience Register

Last updated: 2026-06-29
Owner: Product/Engineering

| Surface | Files | Clarity | Consistency | Accessibility | Professionalism | Test Coverage | Known Limitations | Planned Improvements | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/start` onboarding | `signalrank_telegram/commands.py`, `user_commands.py` | Partial | Partial | Unknown | Partial | Command import/contract tests | Full onboarding journey not snapshotted | Rewrite and snapshot complete journey | Open |
| `/help` and FAQ | `signalrank_telegram/commands.py`, `user_commands.py` | Partial | Partial | Unknown | Partial | Limited | Needs premium, concise, consistent style | Audit and rewrite all help/FAQ copy | Open |
| Signal cards | `signalrank_telegram/formatter.py`, `tier_gated_formatter.py` | Good | Partial | Unknown | Good | Formatter tests | Premium copy not comprehensively audited | Snapshot cards by tier and market state | Open |
| Inline keyboards | `signalrank_telegram/commands.py`, `bot.py` | Improved | Partial | Unknown | Partial | Command contract tests | Full callback map not E2E tested | Add callback inventory and sandbox E2E tests | Open |
| Payment/upgrade flow | `payments`, `paystack`, `signalrank_telegram/commands.py` | Partial | Partial | Unknown | Partial | Enterprise/payment tests | Full conversion copy audit pending | Rewrite and snapshot purchase journey | Open |
| Reports/quality/admin | `signalrank_telegram/commands.py`, `owner_commands.py` | Partial | Partial | Unknown | Partial | Selected tests | Admin UX not fully polished | Add admin workflow UX checklist | Open |
| Error messages | Multiple Telegram/web modules | Partial | Partial | Unknown | Partial | Sparse | Errors vary by subsystem | Standardize human-readable errors | Open |
