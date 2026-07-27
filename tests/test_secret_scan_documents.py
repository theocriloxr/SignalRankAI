from __future__ import annotations

from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "secret_scan.py"


def _scan(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_secret_scan_catches_sensitive_assignment_in_markdown(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        'ADMIN_API_TOKEN="super-' + 'secret-value-123"\n',
        encoding="utf-8",
    )

    result = _scan(tmp_path)

    assert result.returncode == 1
    assert "README.md:1:sensitive_assignment" in result.stdout
    assert ("super-" + "secret-value-123") not in result.stdout


def test_secret_scan_allows_explicit_placeholders(tmp_path: Path):
    (tmp_path / "deployment.env.example").write_text(
        "TELEGRAM_WEBHOOK_SECRET=<GENERATE_RANDOM_SECRET>\n"
        "ADMIN_API_TOKEN=<REDACTED_ROTATE_REQUIRED>\n",
        encoding="utf-8",
    )

    result = _scan(tmp_path)

    assert result.returncode == 0
    assert "PASS findings=0" in result.stdout
