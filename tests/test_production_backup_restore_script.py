"""Execute the restore shell with isolated fake clients; never contact a database."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from tests.test_production_backup_script import posix_path, shell_path

ROOT = Path(__file__).resolve().parents[1]


def run_restore(tmp_path, failure=""):
    binary = tmp_path / "bin"
    binary.mkdir()
    backups = tmp_path / "backups"
    backups.mkdir()
    dump = backups / "signalrank-production-20261004T020138Z.dump"
    dump.write_bytes(b"owned-backup-fixture")
    digest = hashlib.sha256(dump.read_bytes()).hexdigest()
    (backups / "LATEST_BACKUP_FILE.txt").write_text(posix_path(dump) + "\n")
    Path(str(dump) + ".sha256").write_text(f"{digest}  {dump.name}\n")
    Path(str(dump) + ".json").write_text(json.dumps({"alembic_revision": "0045_mt5_credential_retirement"}, separators=(",", ":")))
    if failure == "hash":
        dump.write_bytes(b"corrupted")
    if failure == "path":
        (backups / "LATEST_BACKUP_FILE.txt").write_text("/outside/signalrank-production-20261004T020138Z.dump\n")
    audit = posix_path(tmp_path / "commands")
    common = f'''#!/bin/sh
set -eu
test -z "${{DATABASE_URL+x}}" && test -z "${{PGPASSWORD+x}}" && test -z "${{PGSERVICE+x}}" && test -z "${{OPENAI_API_KEY+x}}"
printf '%s %s\\n' "${{0##*/}}" "$*" >>'{audit}'
'''
    stubs = {
        "id": "echo 0\n",
        "df": "printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 50000000 1000 " + ("1000" if failure == "space" else "49999000") + " 1%% /backup\\n'\n",
        "chown": "exit 0\n",
        "gosu": "shift; exec \"$@\"\n",
        "initdb": "test \"$1\" = -D; mkdir -p \"$2\"; touch \"$2/postgresql.conf\"\n",
        "pg_ctl": "case \"$*\" in *stop*) " + ("exit 1" if failure == "cleanup" else "exit 0") + ";; esac\n",
        "createdb": "test \"$PGHOST\" != remote-production; test \"$PGDATABASE\" = signalrank_restore\n",
        "pg_restore": "case \"$*\" in *--list*) exit 0;; esac; test \"$PGHOST\" != remote-production; test \"$PGDATABASE\" = signalrank_restore; " + ("echo private-error >&2; exit 1" if failure == "restore" else "exit 0") + "\n",
        "psql": '''case "$*" in
*server_version_num*) echo 180006;;
*version_num*) echo ''' + ("wrong_revision" if failure == "revision" else "0045_mt5_credential_retirement") + ''';;
*pg_index*) echo ''' + ("1" if failure == "index" else "0") + ''';;
*pg_constraint*) echo ''' + ("1" if failure == "constraint" else "0") + ''';;
*json_build_object*) echo '{"users":3,"signals":5,"outcomes":2,"signal_deliveries":4}';;
*) exit 2;; esac
''',
    }
    for name, body in stubs.items():
        path = binary / name
        path.write_text(common + body, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    source = (ROOT / "scripts/production_backup_restore.sh").read_text()
    # Only redirect the fixed filesystem root and executable search path in this
    # harness. The actual environment-clearing wrapper executes unchanged.
    source = source.replace("backup_dir=/backup", f"backup_dir='{posix_path(backups)}'")
    source = source.replace("PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", f"PATH='{posix_path(binary)}:/usr/bin:/bin'")
    script = tmp_path / "restore.sh"
    script.write_text(source, encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env.update(DATABASE_URL="forbidden-production", PGPASSWORD="forbidden-secret", PGHOST="remote-production", PGSERVICE="forbidden-service", OPENAI_API_KEY="forbidden-key")
    result = subprocess.run([shell_path(), posix_path(script)], env=env, capture_output=True, text=True, timeout=30)
    commands = (tmp_path / "commands").read_text() if (tmp_path / "commands").exists() else ""
    return result, dump, commands


def test_restore_publishes_only_after_isolated_restore_and_cleanup(tmp_path):
    result, dump, commands = run_restore(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(Path(str(dump) + ".restore.json").read_text())
    assert receipt["restore_verified"] is True
    assert receipt["cleanup_verified"] is True
    assert receipt["production_target_used"] is False
    assert receipt["dump_sha256"] == hashlib.sha256(dump.read_bytes()).hexdigest()
    assert receipt["counts"]["signals"] == 5
    assert not list(dump.parent.glob("restore-drill-*"))
    assert "--dbname=signalrank_restore --no-owner --no-acl --exit-on-error" in commands
    assert "forbidden" not in commands
    assert "remote-production" not in commands


@pytest.mark.parametrize("failure", ["hash", "path", "space", "restore", "revision", "index", "constraint", "cleanup"])
def test_restore_never_certifies_failed_checks_or_deletes_backup(tmp_path, failure):
    result, dump, commands = run_restore(tmp_path, failure)
    assert result.returncode != 0
    assert "BACKUP_RESTORE_PASS" not in result.stdout
    assert not Path(str(dump) + ".restore.json").exists()
    assert dump.is_file()
    assert (dump.parent / "LATEST_BACKUP_FILE.txt").is_file()
    if failure in {"hash", "path", "space"}:
        assert "initdb" not in commands
    if failure == "cleanup":
        assert list(dump.parent.glob("restore-drill-*")), "never delete a possibly running cluster"
    else:
        assert not list(dump.parent.glob("restore-drill-*"))
    if failure == "restore":
        assert Path(str(dump) + ".restore-error.log").read_text().strip() == "private-error"
        assert "private-error" not in result.stdout + result.stderr
