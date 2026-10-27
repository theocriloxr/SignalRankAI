#!/bin/sh
# Read-only logical backup. A valid dump is not proof of a successful restore.
set -eu
umask 077

backup_dir=${BACKUP_DIRECTORY:-/backup}
case "$backup_dir" in /*) ;; *) echo '[backup] backup directory must be absolute' >&2; exit 2 ;; esac
mkdir -p "$backup_dir"
export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-5}"

ready_attempts=${BACKUP_READY_ATTEMPTS:-30}
retry_seconds=${BACKUP_RETRY_SECONDS:-5}
dump_attempts=${BACKUP_DUMP_ATTEMPTS:-3}
for value in "$ready_attempts" "$retry_seconds" "$dump_attempts"; do
    case "$value" in ''|*[!0-9]*|0) echo '[backup] invalid positive retry setting' >&2; exit 2 ;; esac
done

ready=0
attempt=1
while [ "$attempt" -le "$ready_attempts" ]; do
    if pg_isready -q && psql -X -v ON_ERROR_STOP=1 -Atqc 'SELECT 1' >/dev/null; then
        ready=1
        break
    fi
    echo "[backup] database not ready attempt=$attempt/$ready_attempts" >&2
    attempt=$((attempt + 1))
    if [ "$attempt" -le "$ready_attempts" ]; then sleep "$retry_seconds"; fi
done
if [ "$ready" -ne 1 ]; then echo '[backup] readiness exhausted; no successful backup recorded' >&2; exit 1; fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
file="$backup_dir/signalrank-production-$stamp.dump"
pending="$file.partial"
trap 'rm -f -- "$pending" "$pending.toc" "$pending.sha256" "$pending.json"' EXIT
attempt=1
dumped=0
while [ "$attempt" -le "$dump_attempts" ]; do
    echo "[backup] dump attempt=$attempt/$dump_attempts"
    if pg_dump --format=custom --no-owner --no-acl --file="$pending"; then
        dumped=1
        break
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -le "$dump_attempts" ]; then sleep "$retry_seconds"; fi
done
if [ "$dumped" -ne 1 ]; then echo '[backup] dump attempts exhausted; partial artifact discarded' >&2; exit 1; fi
test -s "$pending"
pg_restore --list "$pending" >"$pending.toc"
test -s "$pending.toc"
revision=$(psql -X -v ON_ERROR_STOP=1 -Atqc 'SELECT version_num FROM alembic_version')
case "$revision" in ''|*[!a-zA-Z0-9_]*) echo '[backup] missing or ambiguous Alembic revision' >&2; exit 1 ;; esac
server_major=$(psql -X -v ON_ERROR_STOP=1 -Atqc 'SHOW server_version_num')
case "$server_major" in ''|*[!0-9]*) echo '[backup] invalid PostgreSQL version evidence' >&2; exit 1 ;; esac
digest=$(sha256sum "$pending" | cut -d ' ' -f 1)
created=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '%s  %s\n' "$digest" "$(basename "$file")" >"$pending.sha256"
printf '{"created_at":"%s","alembic_revision":"%s","server_version_num":%s,"dump_sha256":"%s","scope":"LOGICAL_BACKUP_ARTIFACT_ONLY","restore_verified":false}\n' "$created" "$revision" "$server_major" "$digest" >"$pending.json"
mv "$pending.toc" "$file.toc"
mv "$pending.sha256" "$file.sha256"
mv "$pending.json" "$file.json"
# Publish the dump last. Failed attempts cannot replace the last successful dump.
mv "$pending" "$file"
sync
printf '%s\n' "$file" >"$backup_dir/LATEST_BACKUP_FILE.txt.partial"
mv "$backup_dir/LATEST_BACKUP_FILE.txt.partial" "$backup_dir/LATEST_BACKUP_FILE.txt"
echo "[backup] BACKUP_ARTIFACT_PASS file=$file revision=$revision restore_verified=false"
