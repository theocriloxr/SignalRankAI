from __future__ import annotations

from pathlib import Path

from scripts.compile_tracked_python import tracked_python_files
from scripts.generate_repository_proof_manifest import generate

ROOT = Path(__file__).resolve().parents[1]


def test_tracked_compile_scope_excludes_local_virtualenv():
    files = tracked_python_files()
    assert files
    assert all(".venv" not in path.parts and "venv" not in path.parts for path in files)
    assert all(path.is_file() for path in files)


def test_repository_proof_manifest_excludes_local_runtime_state():
    report = generate(ROOT)
    paths = [item["path"].replace("\\", "/") for item in report["files"]]
    assert paths
    forbidden = (".venv/", ".git/", ".freebuff/", ".diagnostics/", "__pycache__/", "logs/")
    assert not any(path.startswith(forbidden) or "/__pycache__/" in path for path in paths)


def test_deployment_diagnostics_uses_tracked_compile_scope():
    source = (ROOT / "scripts/deployment_diagnostics.py").read_text(encoding="utf-8")
    assert "scripts/compile_tracked_python.py" in source
    assert '[python, "-m", "compileall", "-q", "."]' not in source


def test_tracked_compile_scope_falls_back_without_git(monkeypatch):
    import subprocess
    import scripts.compile_tracked_python as compiler

    def no_git(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(compiler.subprocess, "check_output", no_git)
    files = compiler.tracked_python_files()
    assert files
    assert all(path.suffix == ".py" for path in files)
    assert all(not any(part in compiler.SKIP_PARTS for part in path.parts) for path in files)
