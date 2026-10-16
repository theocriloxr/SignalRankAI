# Crash remediation and remaining release work — 3 October 2026

**Live readiness: NO / NOT YET.** The exhaustive directive remains unfinished. No live orders, automatic/copy/prop trading or payouts were enabled. This report supplements the earlier master audit; its production maintenance changes occurred after that audit.

## Verified source

Local candidate: `d1052507210796b1c70ed217fee076eb7a4f7f87`, branch `release/crash-remediation-20261003-r2`, source fingerprint `caa0e29182f9d9f462c119231541a93c9b131b05af164b42bfdd40c49c7713ad`.

The isolated checkout is `.pytest-tmp/crash-final-candidate-20261003`. It is clean. The candidate has not been published or deployed. An external process continues committing/pushing the shared root branch; its commits must not be substituted for this identity. The incremental [Git bundle](../artifacts/crash-remediation-20261003/candidate-d1052507.bundle) was verified and requires the already-public base `ec94f23bd7b0e6a67ca9bac8197eb3797df26df3`.

## Crashed services

### PostgreSQL backup

The supplied failures overlapped the production PostgreSQL shutdown/restart window. The old helper repeatedly exited before PostgreSQL recovered and used the public proxy. The replacement uses private PostgreSQL references, bounded authenticated readiness retries and bounded dump retries. Failed partial files cannot replace a good backup. A published custom-format dump must be nonempty, parse with `pg_restore`, identify one Alembic revision and have a checksum manifest.

Actual Railway backup evidence: `BACKUP_ARTIFACT_PASS` at `2026-10-03T12:05:08Z`, file `/backup/signalrank-production-20261003T120347Z.dump`, revision `0045_mt5_credential_retirement`. **This proves a validated logical artifact, not a production restore.**

Only the backup helper was changed. Its current client image is pinned to `postgres:18@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722`, with `0 2 * * *` cron and `NEVER` restart policy. The first artifact pass predates this image pin; scheduled runtime execution on the newly pinned image still needs observation.

Production native volume backup schedules are configured: daily retention 6 days, weekly 27 days and monthly 89 days. The manual snapshot `7d37ce79-d1cf-462a-978f-ee2f1a42eb6b` exists, and a scheduled daily snapshot completed at `2026-10-03T13:27:01Z`. See [snapshot evidence](../artifacts/crash-remediation-20261003/production-snapshot-read.json) and [schedules](../artifacts/crash-remediation-20261003/backup-schedules-after.json). Custom logical dump-file retention is not yet implemented; old good dumps were preserved.

### SMTP authentication

The helper lacked the SMTP username reference. Its SMTP settings now reference the frontdoor settings, and its preflight runs in a pinned standard-library Python image without importing the application or touching PostgreSQL.

Railway Linux authentication passed with verified TLS at `13:27:59Z` and `13:28:10Z`. [Runtime evidence](../artifacts/crash-remediation-20261003/railway-smtp-authentication.json) explicitly records `email_sent=false`. No email was sent. Authentication-only proof does not establish transactional-email delivery.

### Market certification

`USE_MULTI_PROVIDER_DATA=1` previously missed the string-only `true` comparison and entered legacy routing. Both sync and async paths now use the boolean parser. Expired fallback candles cannot renew their own age during an outage. Unknown, future, forward-filled, analysis-only and capability-mismatched sources cannot pass execution certification.

The connector registry now honors `YFINANCE_ENABLED=0` in adapter and legacy fallback chains. Polygon previously requested the oldest bars in a month-long window. It now requests the newest bars, budgets base aggregates and returns the bounded result in chronological order. Unsupported timeframes return no candles. The [provider API contract](https://massive.com/docs/rest/stocks/aggregates/custom-bars) defines descending order as newest first and its limit in base aggregates.

The final [real network probe](../artifacts/crash-remediation-20261003/local-live-provider-summary.json) certifies crypto only. Equity now returns 200 recent Polygon candles, but they are older than the 750-second freshness limit during Saturday closure. FX, index and commodity have no usable certified candles. This local network evidence does not certify Railway region behavior or open-session freshness. Configured FCS credentials also do not prove a functioning FCS integration.

The pool-cap and background-thread messages in the supplied certification log are configuration diagnostics, not evidence that this job crashed. The certification result itself correctly fails closed when required classes fail.

## Additional defects repaired

- Partial-exit arithmetic rejects invalid direction, stage, stop geometry, target ordering and nonfinite residual marks. Residual losses remain signed. Stored metadata explicitly identifies planned signal exits; actual broker-fill accounting still needs separate acceptance.
- The Telegram/web assertion decodes escaped HTML before checking the account label.
- Governance generation normalizes textual hashes to LF. Its check mode reports differences without rewriting tracked artifacts. Git attributes preserve binary files and explicit shell/Docker LF rules.
- A discovery test no longer performs uncontrolled provider lookups while asserting configured-symbol order.
- Real browser testing exposed PostgreSQL's ambiguous nullable filter parameters. Explicit text casts repair absent filters in signal feed, instrument search and adaptive-profile queries. Real PostgreSQL regressions cover empty and populated filters.
- Workspace navigation handles synchronous and asynchronous loaders without reading `.catch` on `undefined`.
- Workspace dropdowns have accessible names; light-theme text contrast and the clipped evidence volume label were corrected.
- Security gates reject incomplete/malformed audit reports and taint-analysis timeouts. npm advisories are no longer exempted. Runtime and security tooling stay isolated. Docker uses numeric nonroot identity and a pinned base; image/SBOM security acceptance remains incomplete.

## Current validation and limits

| Check | Recorded result | Limit |
| --- | --- | --- |
| [Complete suite](../artifacts/crash-remediation-20261003/release-d1052507-full/complete_system_test_report.json) | 2,403 passed, zero failures/errors/skips; clean source unchanged | Local suite with owned PostgreSQL 17 fixture; no hosted, broker or network-delivery certificate |
| [Browser report](../artifacts/crash-remediation-20261003/browser/report.json) | 38 checks passed; 26 axe scans, zero detected violations | Chromium desktop/mobile viewport, real local HTTP and synthetic user; incomplete axe checks and manual accessibility/device acceptance remain |
| [Static checks](../artifacts/crash-remediation-20261003/static-d1052507.json) | Ruff, Bandit, pip-check, governance pass; critical typing zero errors/one warning | Legacy runtime typing remains 1,501 errors and 53 warnings |
| ShellCheck / Hadolint | All listed shell scripts and both Dockerfiles pass on the preceding source with identical relevant files | APT versions are not fully pinned; final runtime image build, vulnerability scan and reproducible-image proof remain |
| Runtime pip-audit | No known vulnerabilities in the locked Python graph | Dependency metadata is unchanged; OS/image findings are a separate gate |
| [Frontend npm audit](../artifacts/crash-remediation-20261003/frontend-npm-audit.json) | FAIL: 5 high | No unsafe downgrade or advisory exemption applied |
| [Mobile npm audit](../artifacts/crash-remediation-20261003/mobile-npm-audit.json) | FAIL: 16 high, 7 moderate | Native-device and install acceptance remain |
| [Linux Semgrep](../artifacts/crash-remediation-20261003/linux-public-semgrep-result.json) | FAIL: 482 files, zero findings/errors, 19 taint fixpoint timeouts | Diagnostic on public `ec94f23b`, not final candidate; Windows had 387 timeouts; SQL-text audit exclusion still needs disposition |
| [GitHub CI](../artifacts/crash-remediation-20261003/github-ci-billing-current.json) | Jobs never start: billing lock; zero steps | Final candidate has no hosted CI certificate |

The local complete-suite readiness-script pass is a contract check, not this platform's operational readiness verdict. Passing an error budget does not eliminate typing debt. Automated accessibility output does not establish full WCAG compliance.

The Next.js workspace pages are currently descriptive shells. Their typed API client is present but not used by those pages. The browser checks above exercised the canonical FastAPI workspace, not complete functional acceptance of the directive's 27 routes. Neither skeleton pages, mobile exports nor viewport emulation can replace complete product/native E2E.

## Staging database and restore evidence

New persistent PostgreSQL 18 service: `03c04dbd-19f0-484b-b95b-5985a5742124` (`staging-postgres18-durable-20261003`), volume `50bc7d3a-7403-47d2-9b55-9a9d514be222`. It runs PostgreSQL 18.6, matching production's major, and has revision `0048_runtime_schema_bridge`. Direct inspection of both old staging PostgreSQL 16 and the new target records 125 public tables, 3 users and 145 signals.

The guarded transfer script refuses a populated target. These aggregate observations do not prove that this audit performed or validated a complete source-to-target content migration; no successful transfer marker was captured.

An actual [Railway PostgreSQL 18 restore drill](../artifacts/crash-remediation-20261003/staging-restore-counts-result.json) passed in 9 seconds. It dumped the new staging database, restored into a newly created disposable database, checked revision, selected aggregate record counts, 125 tables, 436 indexes and the immutable-ledger trigger, then dropped only its own disposable database. It did not export row contents or verify row fingerprints. It did not restore production data. Its temporary SSH registration was revoked.

Railway returned `NotAuthorized` when configuring staging native backup schedules; staging schedule readback is empty. Access/plan authorization needs resolution. Custom restore evidence does not establish ongoing staging RPO or production disaster recovery.

The four staging application services still use their historical mixed sources and old PostgreSQL route. They have not been switched to the local candidate or the new PostgreSQL target. The unrelated pre-existing staged environment patch was not accepted.

## Remaining acceptance and owner actions

1. Approve publication of exact `d1052507` to `theocriloxr/SignalRankAI`, branch `release/crash-remediation-20261003-r2`. Earlier candidate-publication approval requests are superseded by this identity. Clear the GitHub billing lock and pass required hosted checks on this exact SHA.
2. Resolve frontend/mobile advisories safely, full typing debt, complete Semgrep analysis, SQL-text audit coverage, final image SBOM/vulnerability and reproducibility findings. Review changes against their actual updated source identity.
3. Deploy one immutable certified candidate across all four staging roles. Route to the persistent PostgreSQL 18 target only after appropriate migration/content acceptance. Verify exact source, schema, role ownership, readiness and Redis separation. Do not apply unrelated staged changes.
4. Complete provider-family certification during open sessions and in the deployment region. No freshness relaxation for closed markets. Connect a demo account through the staging UI when its verified endpoint is available; broker credentials do not belong in chat. Prove real demo fills, partial exits, fees/slippage, remaining exposure and broker-confirmed breakeven amendments.
5. Complete operational paper/Telegram/web parity, retries, transport crash/restart, durable queues, Redis-loss and kill-switch drills. Local regressions are retained but do not establish deployed behavior.
6. Complete the 27-route functional browser/mobile acceptance, manual accessibility, native Android/iOS installs and real-device tests. The current Windows environment has no discovered `adb`, emulator or `xcrun` executable.
7. Expand production `Postgres-R8Lr` volume `65b4d299-6d24-4b7a-8a22-7fc42c9c9e58` from 5 GB to at least 10 GB in the [Railway project dashboard](https://railway.com/project/5baa1c14-a748-4dc8-8eb6-411c621e56c3). Last observed use is about 4,503 MB. Available volume-update APIs expose no supported resize field. Verify storage alerts, retention/archive policy and an isolated production restore with adequate disk. No production financial/audit records were deleted.
8. Complete a real 24–72-hour staging soak after mandatory prerequisites pass, with retained measurements, recovery/kill-switch evidence and an unchanged candidate. **Clock not started.**
9. Complete two exhaustive audits that find no new material gaps. **Zero qualifying empty audit passes.** Newly discovered browser/provider defects count as material findings, not empty audits.

The [post-audit flag observations](../artifacts/crash-remediation-20261003/role-financial-flags-after.json) show all four staging and all four production application roles retain disabled real/auto/copy/prop/payout flags and `GLOBAL_EXECUTION_KILL_SWITCH=1`. This is configuration evidence; effective runtime failure enforcement is still an acceptance gate.

Automatic approval review rejected an earlier candidate push as private-code egress and rejected per-table staging fingerprints as sensitive derived-data export. Neither action was retried without approval. Exact candidate publication and the prepared [server-side fingerprint SQL](../artifacts/crash-remediation-20261003/staging-content-fingerprints.sql) remain pending explicit authorization. The approved aggregate-only restore drill is separate evidence with the limited scope stated above.
