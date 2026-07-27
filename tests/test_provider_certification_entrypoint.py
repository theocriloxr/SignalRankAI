from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_provider_certification_runs_as_direct_script(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/certify_providers.py",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    reports = list(tmp_path.glob("*.json"))
    assert reports, result.stdout + result.stderr
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload
