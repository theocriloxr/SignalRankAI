# Connected Access Inventory

Updated: 2026-08-23. This records capability, never secret values. Production mutation remains prohibited without literal `PROMOTE_TO_PRODUCTION`.

| System | Verified | Scope/result |
|---|---:|---|
| Local Git | yes | Read/write on `fix/remaining-staging-blockers` |
| Git remote | yes | Existing remediation branch push succeeds |
| GitHub CLI | no | Stored CLI token expired; Git transport works |
| Railway CLI | yes | Project `trading-bot-account2`, environment `staging` |
| Railway roles | yes | `bountiful-miracle` front door; `striking-optimism` engine; `SignalRankAI` worker |
| PostgreSQL/PgBouncer | yes | Staging schema/seed/structural access; head `0038_account_security_product` |
| Redis | yes | Separate state and delivery services online and ready |
| Telegram | partial | Staging webhook ready; valid-chat acceptance evidence pending |
| Paystack | partial | Key presence only; public payments/transfers disabled; test E2E pending |
| Brokers/providers | partial | Presence/readiness only; real execution prohibited |

Only variable names and presence were inspected. Tokens, passwords, URLs, keys, and connection strings are excluded from evidence and chat output.
