# Disposable production backup restore

`scripts/production_backup_restore.sh` verifies the latest artifact produced by
`scripts/production_backup.sh`. Run both in sequence in the existing pinned
PostgreSQL 18 backup container with its `/backup` volume. Keep the nightly cron
and `NEVER` restart policy; a failed check must remain visible.

The restore phase clears inherited environment variables, verifies the dump's
SHA-256 sidecar and revision, and requires at least 12 GiB free on the backup
volume. It initializes a new PostgreSQL cluster under an owned temporary
directory. That cluster has no TCP listener. Restore clients connect only to its
private Unix socket, role `restore_audit`, database `signalrank_restore`.
Production database credentials are absent from that phase.

The complete archive is restored serially with `--exit-on-error` and a 20-minute
process timeout. Checks compare the restored Alembic revision, reject invalid
indexes and unvalidated constraints, and record counts for users, signals,
outcomes and deliveries. The server must stop and the owned scratch directory
must be removed before a `.dump.restore.json` success receipt is published.
Failed restoration retains a private `.dump.restore-error.log`; it never removes
the backup. A failure to stop the temporary server retains its directory.

`BACKUP_RESTORE_PASS` proves restoration of the identified logical archive into
this disposable instance. It does not prove external disaster recovery, roles
or privileges (the backup omits them), point-in-time recovery, application
cutover, a newer schema migration, or live-trading readiness. The original
artifact manifest remains artifact-only; use the separate restore receipt and
matching digest for restore evidence.

No Railway SSH key or external download of account data is required. Increasing
the production PostgreSQL volume remains a separate operation; free space on
the backup volume does not increase production migration headroom.

The shell tests execute fake PostgreSQL clients and cover environment isolation,
path/hash/headroom failures, restore errors, revision/index/constraint failures,
and safe cleanup. A real restore receipt is still required for operational proof.
