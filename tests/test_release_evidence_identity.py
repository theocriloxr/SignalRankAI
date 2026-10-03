import subprocess

import pytest

from scripts.release_evidence_identity import capture_release_identity, validate_resume_identity, verification_inputs


def test_identity_detects_dirty_source_changes_and_new_files(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "--allow-empty", "-qm", "test"], check=True)
    source = tmp_path / "core"
    source.mkdir()
    initial = capture_release_identity(tmp_path)
    (source / "policy.py").write_text("LIMIT = 1\n", encoding="utf-8")
    added = capture_release_identity(tmp_path)
    assert added["git_sha"] == initial["git_sha"]
    assert added["source_sha256"] != initial["source_sha256"]
    (source / "policy.py").write_text("LIMIT = 2\n", encoding="utf-8")
    assert capture_release_identity(tmp_path)["source_sha256"] != added["source_sha256"]


@pytest.mark.parametrize("changed", ["git_sha", "source_sha256", "branch"])
def test_resume_rejects_previous_candidate(changed):
    identity = {"git_sha": "a" * 40, "source_sha256": "b" * 64, "branch": "release"}
    previous = {"release_identity": {**identity, changed: "different"}, "invocation": {"full": True}}
    with pytest.raises(RuntimeError, match="mismatch"):
        validate_resume_identity(previous, identity, {"full": True})


def test_resume_rejects_old_unidentified_evidence_and_configuration_change():
    with pytest.raises(RuntimeError, match="mismatch"):
        validate_resume_identity({"steps": []}, {"git_sha": "a"}, {})
    with pytest.raises(RuntimeError, match="mismatch"):
        validate_resume_identity({"release_identity": {}, "invocation": {"full": False}}, {}, {"full": True})


def test_resume_accepts_identical_candidate_and_invocation():
    validate_resume_identity({"release_identity": {"git_sha": "a"}, "invocation": {"full": True}},
                             {"git_sha": "a"}, {"full": True})


def test_changed_configuration_invalidates_resume_without_exposing_secrets():
    previous_inputs = verification_inputs({"DATABASE_URL": "postgresql://secret-original"})
    changed_inputs = verification_inputs({"DATABASE_URL": "postgresql://secret-replaced"})
    assert "secret-original" not in str(previous_inputs)
    with pytest.raises(RuntimeError, match="mismatch"):
        validate_resume_identity(
            {"release_identity": {}, "invocation": previous_inputs}, {}, changed_inputs
        )
