# Permission And External Blocker Register

Last updated: 2026-07-26

Secrets must be added directly to sealed staging/Railway variables. They must not be pasted into reports or chat.

| ID | Classification | Required input/permission | Blocks | Work already completed | Owner action |
|---|---|---|---|---|---|
| BLK-001 | PRODUCTION_ACCESS_REQUIRED | Railway staging project and deploy permission | Staging/soak proof | Code, profiles and local verification tooling | Grant staging access or deploy supplied release |
| BLK-002 | SECRET_REQUIRED | Dedicated Telegram test-bot token, webhook secret and test chat IDs | Full command/callback/delivery proof | Hermetic Telegram contracts | Add sealed variables and test identities |
| BLK-003 | SECRET_REQUIRED | Staging PostgreSQL/PgBouncer URL | Real DB compatibility/recovery | Schema/session/migration tests | Provision Railway Postgres reference |
| BLK-004 | SECRET_REQUIRED | Separate RedisState and RedisDelivery URLs | Queue/outage/recovery proof | Redis contracts/stream tests | Provision two Railway Redis services |
| BLK-005 | PROVIDER_CREDENTIAL_REQUIRED | Keys for selected keyed providers | Keyed live certification | Adapters, fixtures and certification framework | Add only selected provider keys |
| BLK-006 | SECRET_REQUIRED | Gemini key and approved bounded budget | Live AI gateway proof | Circuit/fallback tests | Add optional sealed key |
| BLK-007 | OWNER_PERMISSION_REQUIRED | TradingView staging secret/test alert | Signed alert E2E | Route/contracts complete | Send a staging alert after secret set |
| BLK-008 | SECRET_REQUIRED | Paystack test keys and webhook | Payment/reconciliation proof | Payment tests complete | Add test-mode keys only |
| BLK-009 | BROKER_DEMO_ACCOUNT_REQUIRED | MetaApi token and demo account | Broker demo E2E | Broker fail-closed code/tests | Provide demo-only account permission |
| BLK-010 | OWNER_INFORMATION_REQUIRED | Current subscription prices/periods | Public payment activation | Product flows/config ready | Confirm canonical business policy |
| BLK-011 | LEGAL_OR_COMPLIANCE_DECISION_REQUIRED | Retention/privacy/support policy | Public release governance | Safe configurable retention foundation | Supply approved policy |
| BLK-012 | IRREVERSIBLE_ACTION_APPROVAL_REQUIRED | Approval before production migration, user broadcast, payment or real trade | Production changes | Safe deployment/rollback tooling | Explicit approval per action |
