"""The local wrapper must never certify changed or uncommitted source as frozen."""
import json
import subprocess
import sys

import pytest

from scripts import stage1_local_checks as runner


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init")
    git("config", "user.name", "Local verification test")
    git("config", "user.email", "verification@example.invalid")
    (tmp_path / ".gitignore").write_text("artifacts/\n")
    (tmp_path / "source.py").write_text("answer = 1\n")
    git("add", ".")
    git("commit", "-m", "isolated test fixture")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    return tmp_path


def invoke(monkeypatch, code, *, require_clean=True):
    monkeypatch.setattr(sys, "argv", ["stage1_local_checks.py", "--name", "identity",
        *(["--require-clean"] if require_clean else []), "--", sys.executable, "-c", code])
    return runner.main()


def receipt(checkout):
    return json.loads((checkout / "artifacts/stage1-20261014/identity.json").read_text())


def test_clean_source_and_command_result_are_bound(checkout, monkeypatch):
    assert invoke(monkeypatch, "print('one real child process')") == 0
    value = receipt(checkout)
    assert value["source_unchanged"] is True and value["result"] == "PASS"
    assert value["worktree_before"]["dirty"] is False
    assert value["require_clean"] is True


@pytest.mark.parametrize("mutation", [
    "Path('source.py').write_text('answer = 2')",
    "Path('source.py').unlink()",
    "Path('new_source.py').write_text('answer = 3')",
])
def test_successful_child_cannot_certify_changed_source(checkout, monkeypatch, mutation):
    assert invoke(monkeypatch, "from pathlib import Path; " + mutation) == 1
    value = receipt(checkout)
    assert value["command_exit_code"] == 0
    assert value["exit_code"] == 1 and value["result"] == "FAIL"
    assert value["source_unchanged"] is False


def test_dirty_checkout_is_refused_before_child_can_run(checkout, monkeypatch):
    (checkout / "source.py").write_text("changed = True")
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "raise RuntimeError('must not run')")
    assert error.value.code == 2
    assert not (checkout / "artifacts/stage1-20261014/identity.json").exists()


def test_failed_command_remains_failed_with_unchanged_source(checkout, monkeypatch):
    assert invoke(monkeypatch, "raise SystemExit(7)") == 7
    value = receipt(checkout)
    assert value["source_unchanged"] is True
    assert value["command_exit_code"] == value["exit_code"] == 7
    assert value["result"] == "FAIL"
