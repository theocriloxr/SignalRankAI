"""Exercise startup recovery and atomic backup publication with fake client tools."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def shell_path():
    if os.name == "nt":
        path = Path("C:/Program Files/Git/bin/bash.exe")
        if path.is_file(): return str(path)
        pytest.skip("Git Bash required for local shell verification")
    return shutil.which("sh") or pytest.skip("POSIX shell required")


def posix_path(path):
    text = str(path.resolve()).replace("\\", "/")
    return "/" + text[0].lower() + text[2:] if os.name == "nt" else text


def run_backup(tmp_path, *, fail_dump=False, revision="0048_runtime_schema_bridge"):
    binary = tmp_path / "bin"
    binary.mkdir()
    output = tmp_path / "backups"
    output.mkdir()
    stubs = {
        "pg_isready": "count=0; test ! -f \"$STUB_STATE\" || count=$(cat \"$STUB_STATE\"); count=$((count+1)); echo \"$count\" >\"$STUB_STATE\"; test \"$count\" -ge 3\n",
        "psql": f"case \"$*\" in *server_version_num*) echo 180006;; *version_num*) printf '%s\\n' '{revision}';; *) echo 1;; esac\n",
        "pg_dump": "for arg; do case \"$arg\" in --file=*) target=${arg#--file=};; esac; done; echo fixture-dump >\"$target\"; test \"${STUB_DUMP_FAIL:-0}\" != 1\n",
        "pg_restore": "echo '; fixture TOC'\n",
        "sleep": "exit 0\n",
    }
    for name, body in stubs.items():
        path = binary / name
        path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    env = dict(os.environ)
    # Git Bash uses a POSIX PATH; native Windows inherited PATH is translated by
    # MSYS only when unset. Supply the known client-tool fixture and shell tools.
    env["PATH"] = posix_path(binary) + (":/usr/bin:/bin" if os.name == "nt" else ":" + env["PATH"])
    env.update(BACKUP_DIRECTORY=posix_path(output), STUB_STATE=posix_path(tmp_path / "state"),
               BACKUP_READY_ATTEMPTS="4", BACKUP_RETRY_SECONDS="1", BACKUP_DUMP_ATTEMPTS="2",
               STUB_DUMP_FAIL="1" if fail_dump else "0")
    result = subprocess.run([shell_path(), posix_path(ROOT / "scripts/production_backup.sh")],
                            env=env, capture_output=True, text=True, timeout=20)
    return result, output


def test_restart_recovery_waits_then_publishes_one_validated_artifact(tmp_path):
    result, output = run_backup(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "database not ready attempt=2/4" in result.stderr
    assert len(list(output.glob("*.dump"))) == 1
    assert not list(output.glob("*.partial"))
    report = json.loads(next(output.glob("*.dump.json")).read_text())
    assert report["restore_verified"] is False
    assert report["alembic_revision"] == "0048_runtime_schema_bridge"
    assert (output / "LATEST_BACKUP_FILE.txt").is_file()


def test_failed_dump_never_publishes_success_or_partial_artifact(tmp_path):
    result, output = run_backup(tmp_path, fail_dump=True)
    assert result.returncode != 0
    assert "dump attempts exhausted" in result.stderr
    assert "BACKUP_ARTIFACT_PASS" not in result.stdout
    assert not list(output.iterdir())


def test_ambiguous_revision_cannot_create_success_marker(tmp_path):
    result, output = run_backup(tmp_path, revision="0047_event_outbox\n0048_runtime_schema_bridge")
    assert result.returncode != 0
    assert "missing or ambiguous Alembic revision" in result.stderr
    assert not (output / "LATEST_BACKUP_FILE.txt").exists()
    assert not list(output.glob("*.dump"))
