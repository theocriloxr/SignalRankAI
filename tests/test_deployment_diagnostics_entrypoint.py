from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deployment_diagnostics_direct_script_can_import_repository_modules(tmp_path):
    output = tmp_path / "diagnostics.json"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
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
