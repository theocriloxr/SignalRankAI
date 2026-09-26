from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import generate_release_provenance as provenance


COMMIT = "a" * 40
BRANCH = "test/release-provenance"


def test_locked_components_are_unique_and_pinned():
    components = provenance.locked_components()
    assert len(components) >= 50
    keys = [item["name"].lower().replace("_", "-") for item in components]
    assert len(keys) == len(set(keys))
    assert all(item["version"] for item in components)
    assert all(item["purl"].startswith("pkg:pypi/") for item in components)


def test_release_identity_requires_exact_sha():
    commit, branch = provenance.release_identity(COMMIT, BRANCH)
    assert commit == COMMIT
    assert branch == BRANCH
    with pytest.raises(ValueError, match="40_char_sha"):
        provenance.release_identity("abc", BRANCH)


def test_sbom_and_provenance_are_deterministic(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_digests = provenance.write_bundle(first, commit=COMMIT, branch=BRANCH)
    second_digests = provenance.write_bundle(second, commit=COMMIT, branch=BRANCH)

    assert first_digests == second_digests
    for name in ("sbom.cdx.json", "release-provenance.json", "SHA256SUMS"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_provenance_binds_current_release_lock_and_dockerfile(tmp_path: Path):
    provenance.write_bundle(tmp_path, commit=COMMIT, branch=BRANCH)
    report = json.loads((tmp_path / "release-provenance.json").read_text())
    sbom = json.loads((tmp_path / "sbom.cdx.json").read_text())

    assert report["release"]["git_commit"] == COMMIT
    assert report["release"]["git_branch"] == BRANCH
    assert report["release"]["alembic_head"] == "0045_mt5_credential_retirement"
    assert report["inputs"]["requirements.lock"]["sha256"] == provenance.sha256_file(
        provenance.LOCK
    )
    assert report["inputs"]["Dockerfile"]["sha256"] == provenance.sha256_file(
        provenance.DOCKERFILE
    )
    assert report["policy"]["dependency_resolution"] == "locked-no-deps-plus-pip-check"
    assert report["policy"]["artifact_signing"] == "external-key-required"
    assert report["policy"]["live_money_activation_implied"] is False
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"


def test_self_verification_detects_tampering(tmp_path: Path):
    provenance.write_bundle(tmp_path, commit=COMMIT, branch=BRANCH)
    provenance.verify_bundle(tmp_path, commit=COMMIT, branch=BRANCH)

    (tmp_path / "sbom.cdx.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="release_provenance_mismatch:sbom.cdx.json"):
        provenance.verify_bundle(tmp_path, commit=COMMIT, branch=BRANCH)
