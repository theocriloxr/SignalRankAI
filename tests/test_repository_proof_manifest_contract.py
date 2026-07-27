from pathlib import Path

from scripts.generate_repository_proof_manifest import generate


def test_manifest_excludes_generated_manifest_outputs_and_runtime_artifacts(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "core").mkdir()
    (tmp_path / "docs" / "REPOSITORY_PROOF_MANIFEST.json").write_text("{}", encoding="utf-8")
    (tmp_path / "docs" / "REPOSITORY_PROOF_MANIFEST.md").write_text("old", encoding="utf-8")
    (tmp_path / "artifacts" / "large.log").write_text("ignored", encoding="utf-8")
    (tmp_path / "core" / "sample.py").write_text("def public():\n    return 1\n", encoding="utf-8")

    report = generate(tmp_path)
    paths = {item["path"] for item in report["files"]}
    assert "core/sample.py" in paths
    assert "docs/REPOSITORY_PROOF_MANIFEST.json" not in paths
    assert "docs/REPOSITORY_PROOF_MANIFEST.md" not in paths
    assert "artifacts/large.log" not in paths
