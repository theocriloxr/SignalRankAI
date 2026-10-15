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


def test_quoted_identifier_shaped_credentials_are_not_exempt(tmp_path: Path):
    value = "aB7" * 15
    provider = "ghp_" + "Zx8" * 14
    (tmp_path / "config.py").write_text(f'api_key="{value}"\ntoken="{provider}"\n',encoding="utf-8")
    result = _scan(tmp_path)
    assert result.returncode == 1
    assert "generic_api_key" in result.stdout
    assert "github_token" in result.stdout
    assert value not in result.stdout and provider not in result.stdout


def test_provider_test_mode_is_still_a_credential(tmp_path: Path):
    value = "sk_" + "test_" + "aB7" * 15
    (tmp_path / "config.py").write_text(f'credential="{value}"\n',encoding="utf-8")
    result = _scan(tmp_path)
    assert result.returncode == 1
    assert "paystack_secret" in result.stdout
    assert value not in result.stdout


def test_release_scope_keeps_tracked_files_even_in_ignored_directories(tmp_path: Path):
    subprocess.run(["git","init","-q",str(tmp_path)],check=True,capture_output=True)
    (tmp_path / ".gitignore").write_text("generated/\n",encoding="utf-8")
    generated = tmp_path / "generated"
    generated.mkdir()
    secret = 'token="' + "ghp_" + "Qw3" * 14 + '"\n'
    (generated / "ignored.py").write_text(secret,encoding="utf-8")
    assert _scan(tmp_path).returncode == 0
    subprocess.run(["git","add","-f","generated/ignored.py"],cwd=tmp_path,check=True,capture_output=True)
    result = _scan(tmp_path)
    assert result.returncode == 1
    assert "github_token" in result.stdout
