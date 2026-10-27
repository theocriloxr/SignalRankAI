#!/bin/sh
# Logical transfer to an empty, isolated PostgreSQL 18 staging database.
set -eu
umask 077
: "${PGHOST:?source host required}" "${TARGET_PGHOST:?target host required}"
: "${PGUSER:?source user required}" "${PGPASSWORD:?source password required}"
: "${PGDATABASE:?database required}"
if [ "$PGHOST" != staging-postgres.railway.internal ] || [ "$PGDATABASE" != signalrank_staging ]; then
    echo '[staging-transfer] source identity rejected' >&2; exit 2
fi
case "$TARGET_PGHOST" in staging-postgres18-durable-*.railway.internal) ;; *)
    echo '[staging-transfer] target identity rejected' >&2; exit 2 ;; esac
export PGCONNECT_TIMEOUT=5
export PGPORT=5432
export PGSSLMODE=prefer
target_psql() { PGHOST="$TARGET_PGHOST" PGSSLMODE=require psql -X -v ON_ERROR_STOP=1 -Atqc "$1"; }
attempt=0
until target_psql 'SELECT 1' >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then echo '[staging-transfer] target readiness exhausted' >&2; exit 1; fi
    sleep 5
done
major=$(target_psql 'SHOW server_version_num')
case "$major" in 18????) ;; *) echo '[staging-transfer] target is not PostgreSQL 18' >&2; exit 1 ;; esac
objects=$(target_psql "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f') AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e')")
if [ "$objects" != 0 ]; then
    target_psql "SELECT c.relname || ':' || c.relkind::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f') AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e') ORDER BY c.relname LIMIT 20"
    echo '[staging-transfer] target is not empty; refusing overwrite' >&2; exit 1
fi
revision=$(psql -X -v ON_ERROR_STOP=1 -Atqc 'SELECT version_num FROM alembic_version')
if [ "$revision" != 0048_runtime_schema_bridge ]; then echo '[staging-transfer] unexpected source schema' >&2; exit 1; fi
work=$(mktemp -d /tmp/signalrank-staging-transfer.XXXXXX)
trap 'rm -f -- "$work/staging.dump"; rmdir "$work"' EXIT
pg_dump --format=custom --no-owner --no-acl --file="$work/staging.dump"
pg_restore --list "$work/staging.dump" >/dev/null
PGHOST="$TARGET_PGHOST" PGSSLMODE=require pg_restore --exit-on-error --no-owner --no-acl --dbname="$PGDATABASE" "$work/staging.dump"
restored_revision=$(target_psql 'SELECT version_num FROM alembic_version')
if [ "$restored_revision" != "$revision" ]; then echo '[staging-transfer] restored schema mismatch' >&2; exit 1; fi
digest=$(sha256sum "$work/staging.dump" | cut -d ' ' -f 1)
echo "STAGING_PG18_TRANSFER_PASS revision=$revision dump_sha256=$digest production_mutated=false"
