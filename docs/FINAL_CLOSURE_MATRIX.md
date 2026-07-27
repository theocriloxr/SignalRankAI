# SignalRankAI Final Closure Matrix

Date: 2026-07-25

State meanings: `LOCALLY_VERIFIED` means implementation and hermetic/local checks pass. `STAGING_VERIFIED` requires real Railway/provider/Telegram evidence. `SOAK_VERIFIED` requires elapsed soak evidence.

| Requirement | State | Evidence | Remaining release action |
|---|---|---|---|
| Clean deployable source package | LOCALLY_VERIFIED | Source archive excludes real `.env`, `.git`, virtual environments, caches, local DBs and runtime logs | Deploy exact checksum to staging |
| Python compilation | LOCALLY_VERIFIED | Project-wide `compileall` passed | Repeat in CI/Railway build |
| Full local test suite | LOCALLY_VERIFIED | 562 passed, 1 skipped, 0 failed | Run skipped Parquet contract after Railway installs `pyarrow` |
| Schema graph | LOCALLY_VERIFIED | 20 revisions, single head `0020_payment_receipts`, no schema-audit errors | Rehearse against staging database copy |
| Governance validation | LOCALLY_VERIFIED | 17 governance documents validated | Keep registers current after live incidents |
| Secret scan | LOCALLY_VERIFIED | 0 deployable-source findings | Run CI and platform secret scans |
| DB session API | LOCALLY_VERIFIED | Priority/label/timeout contract; legacy production call audit reports 0 | Observe DB admission metrics in Railway |
| Safe staging DB pool | LOCALLY_VERIFIED | Canonical env uses pool 2/overflow 0 | Confirm effective startup log in Railway |
| OHLC asset concurrency | LOCALLY_VERIFIED | Default/effective staging contract set to 2 | Verify real provider in-flight metrics |
| Provider semaphores and bounded attempts | LOCALLY_VERIFIED | Provider-specific locks; maximum two fallback attempts | Exercise live providers and quotas |
| Request coalescing and timeout cleanup | LOCALLY_VERIFIED | Contract tests cover shared owner request and cancellation cleanup | Confirm orphan count 0 in live cycles |
| Required-first timeframe acquisition | LOCALLY_VERIFIED | Required frames precede optional frames | Obtain at least one live `usable=true` asset |
| Canonical asset/session registry | LOCALLY_VERIFIED | 40 registry assets audited; 36 actionable/valid, 4 analysis-only, 0 unsupported | Complete live capability audit per provider |
| Unknown-symbol fail closed | LOCALLY_VERIFIED | Unknowns no longer default to US equity sessions | Watch staging diagnostics |
| Zero-candidate delivery short circuit | LOCALLY_VERIFIED | Audience/DB/background work skipped for empty candidates | Confirm live `[delivery_skipped]` log |
| Single realtime outcome owner | LOCALLY_VERIFIED | Worker owns calculation; Telegram scheduler owns notifications | Confirm startup ownership log |
| Proof-gated live outcomes | LOCALLY_VERIFIED | Live eligibility requires confirmed delivery and Telegram metadata | Verify one natural delivered signal outcome |
| Owner diagnostics | LOCALLY_VERIFIED | Missing-signal, eligibility, OHLC, asset and safe test-delivery commands registered | Exercise through real owner Telegram account |
| Railway entrypoint simulation | LOCALLY_VERIFIED | `/healthz` and webhook ingress pass with real integrations disabled | Deploy to actual Railway staging |
| 100,000-user fanout planning | LOCALLY_VERIFIED | 100,000 unique users, 1,015 batches, 32 shards, no duplicates/missing | Run infrastructure load test and real Telegram sandbox subset |
| Live OHLC/provider path | IMPLEMENTED_UNVERIFIED | Connectors and controls present | Requires Railway credentials/provider network and fresh market evidence |
| Natural strategy signal generation | IMPLEMENTED_UNVERIFIED | Pipeline and tests present | Requires live usable candles and valid market setup |
| Telegram send and delivery proof | IMPLEMENTED_UNVERIFIED | Transaction path and test command present | Requires real bot token/owner chat staging evidence |
| WATCHING_ENTRY to ACTIVE lifecycle | IMPLEMENTED_UNVERIFIED | State/provenance contracts present | Requires genuine post-delivery entry touch |
| Paystack public payments | DEFERRED_APPROVED | Foundations/tests retained; public mutation disabled | Complete sandbox evidence and owner release approval |
| Copy/auto trading | DEFERRED_APPROVED | Foundations retained; default disabled | Separate security, broker sandbox, legal and consent release programme |
| GitHub push/PR | BLOCKED_EXTERNAL | Local branch/commit exists; connector branch write returned 403 and `gh` is unavailable | Enable GitHub App contents/branch write or provide authenticated GitHub CLI environment |
| Live Railway deployment/log monitoring | BLOCKED_EXTERNAL | No Railway connector or authenticated CLI exists in this execution | Connect Railway tooling; deploy exact packaged commit/checksum |
| 24-72 hour owner soak | NOT_STARTED | Cannot be fabricated locally | Start only after staging lifecycle proof |
| Limited/public release | BLOCKED | Release guard intentionally fails without live evidence | Satisfy all staging and soak gates |
