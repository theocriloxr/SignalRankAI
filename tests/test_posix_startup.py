"""Exercise the real entrypoint under POSIX sh with recorded child commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_boot(tmp_path, **settings):
    shell = "C:/Program Files/Git/bin/sh.exe" if os.name == "nt" else shutil.which("sh")
    assert shell and Path(shell).is_file()
    events = tmp_path / "events.jsonl"
    # No database or app import is executed by these contract probes. The shim
    # records arguments and lets each real guard fail at its actual boundary.
    shim = tmp_path / "python"
    shim.write_text("#!/bin/sh\nexec \"" + __import__('sys').executable.replace('\\', '/') + "\" \"" + (tmp_path / "record.py").as_posix() + "\" \"$@\"\n", encoding="utf-8")
    shim.chmod(0o755)
    (tmp_path / "record.py").write_text(
        "import json,os,sys\n"
        "with open(os.environ['BOOT_EVENTS'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "if len(sys.argv)>2 and sys.argv[1]=='-c' and 'lower()' in sys.argv[2]: print(sys.argv[3].lower())\n"
        "raise SystemExit(int(os.environ.get('FAIL_CODE','1')) if os.environ.get('FAIL_COMMAND') in sys.argv[1:] else 0)\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'COMSPEC', 'PATHEXT'}}
    env.update(PATH=str(tmp_path), BOOT_EVENTS=str(events))
    env.update(settings)
    result = subprocess.run([str(shell), str(ROOT / "start.sh")], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=15)
    return result, [json.loads(x) for x in events.read_text().splitlines()] if events.exists() else []


@pytest.mark.parametrize("settings,code,forbidden", [
    ({"SIGNALRANK_IMMUTABLE_RUNTIME": "1", "INSTALL_AT_BOOT": "true"}, 64, "-c"),
    ({"SIGNALRANK_ENV_PROFILE": "production-advisory", "RUN_DB_MIGRATIONS_AT_BOOT": "true"}, 1, "alembic"),
    ({"RAILWAY_PROJECT_ID": "fixture", "FAIL_COMMAND": "scripts/assert_release_source.py"}, 79, "main.py"),
    ({"DATABASE_URL": "postgresql://fixture", "FAIL_COMMAND": "scripts/assert_database_schema.py"}, 78, "main.py"),
    ({"ENVIRONMENT": "PRODUCTION", "RUN_MODE": "frontdoor"}, 80, "main.py"),
    ({"RUN_MODE": "all", "DECOMPOSED_TOPOLOGY_ENABLED": "1"}, 64, "main.py"),
])
def test_guards_stop_before_business_start(tmp_path, settings, code, forbidden):
    result, events = run_boot(tmp_path, **settings)
    assert result.returncode == code, result.stderr
    assert not any(forbidden in command for command in events)


@pytest.mark.parametrize("role", ["web", "engine", "worker", "analytics", "delivery", "outcome"])
def test_decomposed_roles_start_only_the_designated_process(tmp_path, role):
    result, events = run_boot(tmp_path, RUN_MODE=role, RAILWAY_SERVICE_NAME="fixture",
                              HONOR_RUN_MODE_ON_RAILWAY="1")
    assert result.returncode == 0, result.stderr
    assert events[-1] == ["main.py"]
    assert ["scripts/assert_release_source.py"] in events


def test_migration_role_runs_guarded_owner_and_does_not_start_app(tmp_path):
    result, events = run_boot(tmp_path, SERVICE_ROLE="migration", RAILWAY_PROJECT_ID="fixture")
    assert result.returncode == 0, result.stderr
    assert events[-1][:2] == ["scripts/controlled_migrate.py", "--output"]
    assert ["main.py"] not in events


def test_quiescent_role_starts_after_schema_guard(tmp_path):
    result, events = run_boot(tmp_path, SIGNALRANK_QUIESCENT_CERTIFICATION="1", DATABASE_URL="postgresql://fixture")
    assert result.returncode == 0, result.stderr
    assert ["scripts/assert_database_schema.py"] in events
    assert events[-1] == ["-u", "-m", "scripts.quiescent_role"]
