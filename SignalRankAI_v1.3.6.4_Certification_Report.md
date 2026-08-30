# SignalRankAI v1.3.6.4 Source Certification Report

## Scope

Certification was performed against the exact v1.3.6 Railway Performance Decomposition release archive supplied in the user's file library.

## Verified fixes

| Finding | Source-level result |
|---|---|
| `/performance` duplicate ledger traceback | Atomic PostgreSQL conflict handling implemented |
| Staging records/locks scoped as production | Railway environment metadata made authoritative |
| Multiple resend owners | Shared project/environment/job lease implemented |
| Scheduler executions exceed interval | Work budgets, smaller batches, longer intervals, coalescing implemented |
| Outcome notification duplicate ownership | Shared distributed lease implemented |
| Per-recipient repeated market fetch | Changed to one fetch per outcome |
| Unconfigured provider timeout waste | Keyed providers removed from routes when unconfigured |
| XAGUSD trusted route absent | MetaApi/OANDA/Twelve Data/FCS routes added before Yahoo |
| FCS API incompatibility | v4 `/forex/latest` contract implemented and tested |
| Production accepts partial provider coverage | `/readyz` provider-coverage gate added |

## Test results

- Focused regression suite: **78 passed**.
- Expanded relevant suite: **111 passed, 3 deselected**.
- Hotfix-specific tests: **10 passed**.
- Provider hotfix subset: **46 passed**.
- Python `compileall`: **passed**.
- Patch application against pristine v1.3.6 plus compilation: **passed**.
- Scheduler lease smoke test: **passed**.

The three deselected tests import `railway_main` and require APScheduler. The offline validation container did not contain that dependency and had no package-index access. APScheduler is already declared in the project's `requirements.txt` and was present in the successful Railway runtime logs.

## Limitations

This report certifies the source artifact, not the live Railway deployment. Final production certification requires:

1. Deployment of the same commit to all three services.
2. Rotation of credentials previously exposed in copied terminal output.
3. A configured trusted FX/metals provider.
4. Runtime confirmation that `/performance` no longer raises a duplicate-ledger error.
5. Runtime confirmation that scheduler jobs remain within their intervals.
6. Production `/readyz` reporting `checks.provider_coverage.complete=true`.
