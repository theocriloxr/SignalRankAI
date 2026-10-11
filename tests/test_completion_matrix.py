from copy import deepcopy
import shutil

import pytest

from scripts.completion_matrix import ROOT, build, source_inventory, validate_disposition


def test_every_preserved_section_and_master_clause_retains_its_source_and_subrequirements():
    matrix = build()
    entries = matrix["entries"]
    assert len(entries) == 991 and len({x["id"] for x in entries}) == 991
    assert len([x for x in entries if "specs/20261005" in x["source"]]) == 560
    assert not matrix["inventory_is_acceptance"]
    assert matrix["research_source"]["status"] == "SUPPLIED_CONTENT_REVIEW_COMPLETE"
    assert all(x["text"] and x["text_sha256"] and x["subrequirements"] for x in entries)
    assert all(not x["acceptance"]["status"].startswith("VERIFIED") for x in entries)


@pytest.fixture
def copied_sources(tmp_path):
    for path in (ROOT / "docs/specs/20261005").iterdir():
        target = tmp_path / "docs/specs/20261005" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    for name in ["docs/SIGNALRANKAI_MASTER_DIRECTIVE_20261002.txt", "certification/master_requirement_registry.json"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def test_source_content_changes_cannot_silently_drop_requirements(copied_sources):
    path = copied_sources / "docs/specs/20261005/research-validation.md"
    path.write_text(path.read_text("utf-8").replace("# 22. DATA POINT-IN-TIME CORRECTNESS", "# Removed"), encoding="utf-8")
    with pytest.raises(ValueError, match="hash_mismatch"):
        source_inventory(copied_sources)


def test_original_crlf_attachment_hashes_and_git_lf_sources_are_both_accepted(copied_sources):
    for path in (copied_sources / "docs/specs/20261005").glob("*.md"):
        path.write_bytes(path.read_text("utf-8").replace("\n", "\r\n").encode())
    assert len(source_inventory(copied_sources)) == 991


def disposition(entry):
    return {"status": "VERIFIED_CI", "text_sha256": entry["text_sha256"], "canonical_paths": [],
        "missing_acceptance": [], "evidence": [{"sha": "a" * 40, "environment": "hosted_ci",
            "timestamp": "2026-10-10T14:00:00Z", "command": "owned acceptance command",
            "artifact": "https://github.com/theocriloxr/SignalRankAI/actions/runs/38056860381",
            "result": "PASS", "scope": "VERIFIED_CI", "subrequirements": [x["id"] for x in entry["subrequirements"]]}]}


@pytest.mark.parametrize("mode", ["empty", "missing_clause", "stale_text", "skip", "scope", "short_sha", "missing_artifact", "missing_acceptance"])
def test_inventoried_or_partially_tested_work_cannot_become_a_verified_section(mode):
    entry = source_inventory(ROOT)[0]
    value = deepcopy(disposition(entry))
    if mode == "empty":
        value["evidence"] = []
    elif mode == "missing_clause":
        value["evidence"][0]["subrequirements"].pop()
    elif mode == "stale_text":
        value["text_sha256"] = "b" * 64
    elif mode == "skip":
        value["evidence"][0]["result"] = "SKIP"
    elif mode == "scope":
        value["evidence"][0]["scope"] = "VERIFIED_LOCAL"
    elif mode == "short_sha":
        value["evidence"][0]["sha"] = "e1803431"
    elif mode == "missing_artifact":
        value["evidence"][0].pop("artifact")
    else:
        value["missing_acceptance"] = ["native device behavior"]
    with pytest.raises(ValueError):
        validate_disposition(value, entry, ROOT)


def test_missing_implementation_paths_or_unactionable_external_blockers_are_rejected():
    entry = source_inventory(ROOT)[0]
    value = disposition(entry) | {"status": "PARTIAL", "canonical_paths": ["missing_implementation.py"]}
    with pytest.raises(ValueError, match="path_missing"):
        validate_disposition(value, entry, ROOT)
    value = disposition(entry) | {"status": "BLOCKED_EXTERNAL", "external": {"cause": "upstream"}}
    with pytest.raises(ValueError, match="action_and_retry"):
        validate_disposition(value, entry, ROOT)
