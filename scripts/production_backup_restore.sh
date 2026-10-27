#!/bin/sh
# Restore only our own backup into a disposable, socket-only PostgreSQL instance.
# Inherited production credentials and connection options never reach this phase.
set -eu
exec env -i PATH=/usr/lib/postgresql/18/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/tmp LANG=C.UTF-8 /bin/sh -s <<'RESTORE_ISOLATED'
set -eu
umask 077
phase=preflight
trap 'code=$?; if [ "$code" != 0 ]; then echo "[restore] failed phase=$phase code=$code" >&2; fi' EXIT
for client in pg_restore initdb pg_ctl psql createdb gosu timeout; do
    command -v "$client" >/dev/null || { echo "[restore] missing client=$client" >&2; exit 2; }
done
backup_dir=/backup
test "$(id -u)" = 0
test -d "$backup_dir" && test ! -L "$backup_dir"
test "$(realpath "$backup_dir")" = "$backup_dir"
file=$(cat "$backup_dir/LATEST_BACKUP_FILE.txt")
name=${file##*/}
case "$name" in signalrank-production-????????T??????Z.dump) ;; *) echo '[restore] invalid backup name' >&2; exit 2 ;; esac
test "$file" = "$backup_dir/$name"
test -s "$file" && test ! -L "$file"
test -s "$file.sha256" && test ! -L "$file.sha256"
test -s "$file.json" && test ! -L "$file.json"
digest=$(sha256sum "$file" | cut -d ' ' -f 1)
test "$(cat "$file.sha256")" = "$digest  $name"
revision=$(sed -n 's/.*"alembic_revision":"\([a-zA-Z0-9_]*\)".*/\1/p' "$file.json")
case "$revision" in ''|*[!a-zA-Z0-9_]*) echo '[restore] invalid backup revision' >&2; exit 2 ;; esac
# Reserve at least 12 GiB for a serial restore of the current roughly 4.5 GiB DB.
available_kb=$(df -Pk "$backup_dir" | awk 'NR==2 {print $4}')
case "$available_kb" in ''|*[!0-9]*) exit 2 ;; esac
if [ "$available_kb" -lt 12582912 ]; then echo '[restore] insufficient scratch headroom' >&2; exit 1; fi
pg_restore --list "$file" >/dev/null

scratch=$(mktemp -d "$backup_dir/restore-drill-XXXXXXXX")
token=${scratch##*/}
printf '%s\n' "$token" >"$scratch/.owned-restore-drill"
started=0
cleanup() {
    code=$?
    trap - EXIT HUP INT TERM
    if [ "$code" != 0 ]; then echo "[restore] failed phase=$phase code=$code" >&2; fi
    # Never remove an arbitrary path, a symlink, a backup, or a running cluster.
    case "$scratch" in "$backup_dir"/restore-drill-*) ;; *) exit 2 ;; esac
    if [ -L "$scratch" ] || [ "$(realpath "$scratch")" != "$scratch" ] ||
       [ "$(cat "$scratch/.owned-restore-drill")" != "$token" ]; then exit 2; fi
    if [ "$started" = 1 ]; then
        if ! gosu postgres pg_ctl -D "$scratch/data" -m immediate -t 60 -w stop >"$scratch/stop.log" 2>&1; then
            echo '[restore] cleanup failed; isolated cluster retained for investigation' >&2
            exit 1
        fi
    fi
    rm -rf -- "$scratch"
    exit "$code"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
mkdir "$scratch/socket"
chown postgres:postgres "$scratch" "$scratch/socket"
phase=initialize
if ! gosu postgres initdb -D "$scratch/data" --username=restore_audit --auth-local=trust --auth-host=reject --no-locale --encoding=UTF8 >"$scratch/init.log" 2>&1; then
    # This is an empty cluster; initialization diagnostics contain no restored rows.
    cat "$scratch/init.log" >&2
    exit 1
fi
# No network listener; the only connection path is inside the owned 0700 dir.
cat >>"$scratch/data/postgresql.conf" <<CONFIG
listen_addresses = ''
unix_socket_directories = '$scratch/socket'
port = 55432
max_connections = 10
shared_buffers = '32MB'
maintenance_work_mem = '32MB'
max_parallel_workers = 0
statement_timeout = '15min'
CONFIG
started=1
phase=start
if ! gosu postgres pg_ctl -D "$scratch/data" -l "$scratch/server.log" -t 60 -w start >"$scratch/start.log" 2>&1; then
    cat "$scratch/start.log" >&2
    exit 1
fi
export PGHOST="$scratch/socket" PGPORT=55432 PGUSER=restore_audit PGDATABASE=signalrank_restore PGCONNECT_TIMEOUT=5
createdb --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --maintenance-db=postgres signalrank_restore
phase=restore
echo "[restore] restoring digest=$digest into disposable socket-only database"
if ! timeout --kill-after=30s 1200s pg_restore --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname=signalrank_restore --no-owner --no-acl --exit-on-error "$file" >"$scratch/restore.log" 2>&1; then
    cp "$scratch/restore.log" "$file.restore-error.log"
    echo '[restore] failed; private restore-error.log retained beside backup; no success receipt' >&2
    exit 1
fi
sql() { psql -X -v ON_ERROR_STOP=1 -Atqc "$1"; }
phase=verify
test "$(sql 'SELECT version_num FROM alembic_version')" = "$revision"
test "$(sql 'SELECT count(*) FROM pg_index WHERE NOT indisvalid OR NOT indisready')" = 0
test "$(sql 'SELECT count(*) FROM pg_constraint WHERE NOT convalidated')" = 0
# Aggregate evidence only: no account rows or credentials are logged.
counts=$(sql "SELECT json_build_object('users', (SELECT count(*) FROM users), 'signals', (SELECT count(*) FROM signals), 'outcomes', (SELECT count(*) FROM outcomes), 'signal_deliveries', (SELECT count(*) FROM signal_deliveries))")
server_version=$(sql 'SHOW server_version_num')
case "$server_version" in ''|*[!0-9]*) exit 2 ;; esac
phase=stop
gosu postgres pg_ctl -D "$scratch/data" -m fast -t 60 -w stop >"$scratch/stop.log" 2>&1
started=0
# Cleanup before success publication, with the same containment/ownership checks.
test ! -L "$scratch" && test "$(realpath "$scratch")" = "$scratch"
test "$(cat "$scratch/.owned-restore-drill")" = "$token"
rm -rf -- "$scratch"
trap - EXIT HUP INT TERM
created=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '{"created_at":"%s","alembic_revision":"%s","dump_sha256":"%s","server_version_num":%s,"scope":"DISPOSABLE_LOCAL_SOCKET_RESTORE","restore_verified":true,"cleanup_verified":true,"production_target_used":false,"counts":%s}\n' "$created" "$revision" "$digest" "$server_version" "$counts" >"$file.restore.json.partial"
mv "$file.restore.json.partial" "$file.restore.json"
sync
echo "[restore] BACKUP_RESTORE_PASS digest=$digest revision=$revision cleanup_verified=true production_target_used=false"
cat "$file.restore.json"
RESTORE_ISOLATED
