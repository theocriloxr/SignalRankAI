"""Synthetic private sources test lossless intake and fail-closed certification."""
import csv
import json
from zipfile import ZipFile

import pytest

from scripts import crosschat_intake as intake


def csv_file(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def bundle(tmp_path):
    (tmp_path / "sources").mkdir()
    (tmp_path / "indexes").mkdir()
    for name in ("README.md", "START_HERE_MASTER_CODEX_PROMPT.md", "START_CODEX_MESSAGE.txt"):
        (tmp_path / name).write_text("Private instruction fixture", encoding="utf-8")
    text = "Private original fixture; never publish this wording"
    docx = tmp_path / "sources/source.docx"
    with ZipFile(docx, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>')
    export = tmp_path / "sources/source.txt"
    export.write_text("[SOURCE BLOCK 1 | Heading 1 | [PREFACE]]\n" + text + "\n\n", encoding="utf-8")
    csv_file(tmp_path / "indexes/source_clauses.csv", [dict(source="source.docx", block_id="1", kind="PARAGRAPH",
             style="Heading 1", section_context="[PREFACE]", sha256=intake.sha(text), text=text, status="UNASSESSED")])
    csv_file(tmp_path / "indexes/source_headings.csv", [dict(source="source.docx", index="1", heading=text, style="Heading 1")])
    csv_file(tmp_path / "indexes/known_requirements_seed.csv", [dict(id="SEED-1", original_or_summary="private seed fixture", domain="PRIVATE")])
    manifest = {"source_clause_rows": 1, "headings": 1, "historical_seed_rows": 1, "source_documents": [{
        "filename": "source.docx", "extracted_text_filename": "source.txt", "sha256_original": intake.sha(docx.read_bytes()),
        "sha256_text": intake.sha(export.read_bytes()), "paragraph_and_table_row_count": 1, "section_heading_count": 1}]}
    (tmp_path / "indexes/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_complete_original_export_and_indexes_are_ingested_without_publishing_private_words(bundle):
    snapshot, private = intake.ingest(bundle, [])
    assert snapshot["counts"] == {"clauses": 1, "headings": 1, "seeds": 1}
    assert snapshot["documents"][0]["full_export_matches_ledger"] is True
    public = intake.canonical(snapshot)
    for secret in ("Private original fixture", "private seed fixture", "Private instruction fixture"):
        assert secret not in public
        assert secret in intake.canonical(private)
    assert snapshot["documents"][0]["semantic_review_complete"] is False
    rows, coverage = intake.build(snapshot, {"requirements": [], "interfaces": []}, {})
    assert all(r["status"] == "INCOMPLETE" and r["runtime_proof"] == [] for r in rows)
    assert coverage["unclassified_applicable"] == len(rows)
    assert coverage["release_decision"] == "NO-GO"


@pytest.mark.parametrize("mutation,match", [
    ("missing_clause", "source_count"), ("bad_hash", "export_clause_or_hash"),
    ("wrong_text", "original_document_clause"), ("duplicate_id", "source_block_sequence"),
    ("wrong_heading", "heading_not_in_original"), ("wrong_source", "unexpected_or_missing"),
    ("wrong_export", "original_or_export_hash"), ("traversal", "unsafe_source_filename"),
])
def test_missing_tampered_or_reordered_source_is_rejected(bundle, mutation, match):
    clauses = bundle / "indexes/source_clauses.csv"
    rows = intake.read_csv(clauses)
    if mutation == "missing_clause":
        clauses.write_text(",".join(rows[0])+"\n", encoding="utf-8")
    elif mutation in {"bad_hash", "wrong_text", "duplicate_id", "wrong_source"}:
        field = {"bad_hash": "sha256", "wrong_text": "text", "duplicate_id": "block_id", "wrong_source": "source"}[mutation]
        rows[0][field] = "changed"
        csv_file(clauses, rows)
    elif mutation == "wrong_heading":
        path = bundle / "indexes/source_headings.csv"
        headings = intake.read_csv(path)
        headings[0]["heading"] = "not present"
        csv_file(path, headings)
    elif mutation == "wrong_export":
        (bundle / "sources/source.txt").write_text("replaced", encoding="utf-8")
    elif mutation == "traversal":
        for name in ("source_clauses.csv", "source_headings.csv"):
            path = bundle / "indexes" / name
            content = intake.read_csv(path)
            content[0]["source"] = "../source.docx"
            csv_file(path, content)
        path = bundle / "indexes/manifest.json"
        manifest = json.loads(path.read_text("utf-8"))
        manifest["source_documents"][0]["filename"] = "../source.docx"
        path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        intake.ingest(bundle, [])


def test_historical_verified_label_cannot_become_current_acceptance(bundle):
    snapshot, _ = intake.ingest(bundle, [])
    prior = {"id": "OLD-1", "kind": "SOURCE", "source": "old-report.md", "status": "VERIFIED",
             "responsible_component": "past", "test_evidence": ["historical PASS"]}
    rows, coverage = intake.build(snapshot, {"requirements": [prior], "interfaces": []}, {})
    assert rows[-1]["status"] == "INCOMPLETE"
    assert rows[-1]["prior_status"] == "VERIFIED"
    assert coverage["implemented_and_verified"] == 0


@pytest.mark.parametrize("change,match", [
    ({"source_sha256": "stale"}, "stale_source"),
    ({"status": "IMPLEMENTED_AND_VERIFIED", "proofs": []}, "verification_incomplete"),
    ({"status": "EXTERNALLY_BLOCKED"}, "external_blocker_incomplete"),
    ({"status": "SUPERSEDED"}, "precedence_target"),
    ({"status": "DUPLICATED"}, "precedence_target"),
    ({"code": ["../outside.py"]}, "missing_or_external"),
])
def test_disposition_cannot_hide_unproven_scope(bundle, change, match):
    snapshot, _ = intake.ingest(bundle, [])
    row = snapshot["records"][0]
    review = {"source_sha256": row["source_sha256"], "status": "INCOMPLETE", "reviewer": "synthetic test",
              "acceptance": "Document a specific criterion", **change}
    with pytest.raises(ValueError, match=match):
        intake.build(snapshot, {"requirements": [], "interfaces": []}, {row["id"]: review}, bundle)


def test_sanitized_snapshot_and_review_cannot_silently_drop_rows(bundle):
    snapshot, _ = intake.ingest(bundle, [])
    with pytest.raises(ValueError, match="orphan_review"):
        intake.build(snapshot, {"requirements": [], "interfaces": []}, {"absent": {}})
    snapshot["records"].pop()
    with pytest.raises(ValueError, match="integrity_mismatch"):
        intake.build(snapshot, {"requirements": [], "interfaces": []}, {})


def test_committed_crosschat_outputs_are_current_and_private_bundle_is_not_tracked():
    import subprocess

    result = subprocess.run(["git", "ls-files", "SignalRankAI_Complete_CrossChat_Codex_Handoff_*"],
                            cwd=intake.ROOT, capture_output=True, text=True, check=True)
    assert not result.stdout.strip()
    snapshot = json.loads((intake.ROOT / intake.INDEX).read_text("utf-8"))
    inventory = json.loads((intake.ROOT / "docs/release/requirements.json").read_text("utf-8"))
    reviews = json.loads((intake.ROOT / intake.DISPOSITIONS).read_text("utf-8"))["entries"]
    rows, coverage = intake.build(snapshot, inventory, reviews)
    actual = [json.loads(line) for line in (intake.ROOT / "docs/release/requirements_universe.jsonl").read_text("utf-8").splitlines()]
    assert actual == rows
    assert json.loads((intake.ROOT / "docs/release/source_coverage.json").read_text("utf-8")) == coverage


def test_continuation_artifacts_match_retained_hashes():
    import subprocess

    index = json.loads((intake.ROOT / "docs/release/evidence/continuation-20261016/index.json").read_text("utf-8"))
    for artifact in index["artifacts"]:
        path = intake.ROOT / artifact["path"]
        assert intake.sha(path.read_bytes()) == artifact["sha256"]
        assert path.stat().st_size == artifact["bytes"]
        # A local ignored .log is not retained evidence in another checkout.
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", artifact["path"]],
                                 cwd=intake.ROOT, capture_output=True)
        assert tracked.returncode == 0, artifact["path"]
