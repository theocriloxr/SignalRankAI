# Production recovery and provider repair — 3 October 2026

Requested branch: `fix/provider-discovery-readiness-20260923`.
Inspected branch head: `57a2f46bc3085ccef2892013e378b080ad13f82c`.
Live and funded-prop readiness: **NO / NOT YET**. The user authorized activation
only after readiness and requested paper trading first. No financial switches
were enabled by this repair.

## Production incident

An external deployment put `57a2f46b` into services pinned to `8f858393`.
Release-source admission correctly stopped the workers. Snapshot rollback lost
Railway Git metadata and was rejected too. Explicit builds of the previously
running `8f8583933a853a54ba1b3585610ee466903c08fc` recovered worker, engine and
analytics. The existing frontdoor continued serving HTTP 200 at `/healthz` and
`/readyz` with matching revision `0045_mt5_credential_retirement`.

Staging was initially updated toward `57a2f46b`; the owner then confirmed its
deletion and directed further work to production. No staging certificate or soak
is claimed. Other connected repositories were inventoried separately; their
services must not receive SignalRankAI source.

## Repairs in this candidate

- Twelve Data adapters and legacy routing share quota cooldowns. HTTP 429 or a
  quota rejection cannot repeatedly call the provider within that process's
  cooldown. Credentials and request URLs are excluded from error logs.
- Both paths request UTC timestamps and respect explicit offsets. Currency and
  metal pairs use slash notation; equity punctuation is preserved. The alternate
  API-key name is accepted; unsupported timeframes fail closed.
- Production migration admission requires a recent observation of actual volume
  capacity and reserves space for the existing rejection relation, its JSONB
  copy and WAL. It checks under the advisory lock before Alembic mutates schema.
  This is a conservative estimate, not a filesystem free-space certificate.
- The rejection tracker detects the 0046 computed view and persists labels in
  its owning `decision_log` JSONB record. Existing metadata survives. It commits
  before reporting success; legacy physical-table tracking remains supported.

The configured Twelve Data key returned daily-quota exhaustion: over 1,870 used
against 800 permitted credits. This requires a suitable provider allowance and
shared request budgeting, not a freshness exemption. The actual Railway class
certificate passed crypto only; FX, index and commodity were empty and equity
was stale during Saturday closure.

## Production upgrade blockers

The inspected database was PostgreSQL 18.6, revision 0045, about 4.21 GB of
database files on a 5 GB volume. Catalog observations put `decision_log` at
1.52 GB and `ml_rejected_signals` at 1.50 GB. Migration 0046 copies the latter
before dropping its physical table. Running it with approximately 0.5 GB of
remaining volume capacity risks exhausting disk. The owner must expand the
volume to at least 10 GB and provide fresh capacity evidence before upgrading.
Retained native snapshots were confirmed; a production restore is not certified.

The production upgrade must use one controlled migration owner, a recent
validated backup, exact source identity, the observed capacity inputs and a
verified post-upgrade schema. Then all four application roles must use the same
candidate. Never turn off source/schema admission to make a deployment green.

Still open: hosted CI billing; frontend/mobile security advisories; complete
typing and Semgrep coverage; final image security/reproducibility; provider and
broker certification; effective kill/recovery/Redis behavior; full functional
web/native acceptance; ongoing storage/retention/alerts and disaster recovery;
soak and two exhaustive audits without new material gaps. A funded prop account
uses the live-money gates. Local tests cannot certify actual broker fills or
the readiness of a funded account.
