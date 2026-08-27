from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_proof_manifest_uses_git_tracked_files() -> None:
    source = (ROOT / "scripts" / "generate_repository_proof_manifest.py").read_text(encoding="utf-8")
    assert '["git", "ls-files", "-z"]' in source
    assert "for path in _repository_files(root)" in source


def test_deployment_diagnostics_direct_script_can_import_repository_modules(tmp_path):
    output = tmp_path / "diagnostics.json"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    # This test proves direct-script imports and report creation, not access to
    # whichever live services happen to be configured in the invoking shell.
    for name in (
        "DATABASE_URL", "DATABASE_PRIVATE_URL", "DATABASE_PUBLIC_URL",
        "STATE_REDIS_URL", "DELIVERY_REDIS_URL", "REDIS_URL",
        "TELEGRAM_BOT_TOKEN",
    ):
        env.pop(name, None)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/deployment_diagnostics.py",
            "--phase",
            "predeploy",
            "--continue-on-failure",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    # Missing live credentials may make the diagnostic verdict non-zero, but
    # the orchestrator itself must finish and retain a parseable report.
    assert "ModuleNotFoundError: No module named 'core'" not in result.stdout + result.stderr
    assert output.exists(), result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["checks"]
    route = next(item for item in payload["checks"] if item["name"] == "fastapi_route_inventory")
    assert route["status"] in {"PASS", "FAIL"}
    assert "No module named 'core'" not in route["detail"]
