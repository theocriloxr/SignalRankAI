"""Lossless acceptance inventory; neither file discovery nor CI confers completion.

Run as `python -m scripts.completion_matrix [--check]`. Reviewed dispositions are
separate from the preserved prompts and historical registries. The check rejects
lost sections/subrequirements, stale source hashes, and unsupported green claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from scripts.build_master_requirement_registry import inventory

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = "certification/completion_matrix.json"
REPORT = "docs/COMPLETION_MATRIX.md"
DISPOSITIONS = "certification/completion_dispositions.json"
COUNTS = {"research-validation.md": 43, "customer-execution-experience.md": 82,
          "completion-and-resilience.md": 238, "web-mobile-design.md": 115,
          "multi-broker-gap-closure.md": 82}
STATUSES = {"AUDIT_PENDING", "UNIMPLEMENTED", "PARTIAL", "IMPLEMENTED_UNVERIFIED",
            "VERIFIED_LOCAL", "VERIFIED_CI", "VERIFIED_STAGING", "BLOCKED_EXTERNAL"}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def source_inventory(root: Path) -> list[dict[str, Any]]:
    manifest = json.loads((root / "docs/specs/20261005/source-manifest.json").read_text("utf-8"))
    entries = []
    counts = {}
    for source in manifest["sources"]:
        path = "docs/specs/20261005/" + source["file"]
        text = (root / path).read_text("utf-8")
        # The attachment manifest hashes original CRLF bytes; Git enforces LF
        # for these files. Accept only this explicit, lossless EOL conversion.
        if source["sha256"] not in {_hash(text), _hash(text.replace("\n", "\r\n"))}:
            raise ValueError("preserved_specification_hash_mismatch:" + path)
        lines = text.splitlines()
        counts[source["file"]] = len(source["sections"])
        actual = [(i, line) for i, line in enumerate(lines, 1) if re.match(r"^# \d+\. ", line)]
        expected = [(section["line_start"], section["heading"]) for section in source["sections"]]
        if actual != expected:
            raise ValueError("specification_section_inventory_mismatch:" + path)
        for section in source["sections"]:
            start, end = section["line_start"], section["line_end"]
            number = re.match(r"^# (\d+)\.", section["heading"])[1]
            identifier = path + "#" + number
            body = "\n".join(lines[start - 1:end])
            # Preserve every substantive line, including instructions within
            # examples and lists. Grouping/review must not delete source clauses.
            units = [{"id": identifier + f":L{line}", "line": line, "text": lines[line - 1]}
                     for line in range(start + 1, end + 1)
                     if lines[line - 1].strip() and lines[line - 1].strip() not in {"---", "```", "```text"}]
            entries.append({"id": identifier, "source": path, "source_sha256": source["sha256"],
                "canonical_lf_sha256": _hash(text), "source_hash_convention": "original_attachment_bytes; repository_eol_lf",
                "line_start": start, "line_end": end, "heading": section["heading"],
                "text": body, "text_sha256": _hash(body), "subrequirements": units,
                "historical_disposition_reference": "docs/specs/20261005/source-manifest.json"})
    if counts != COUNTS:
        raise ValueError("expected_560_preserved_sections")
    master_path = "docs/SIGNALRANKAI_MASTER_DIRECTIVE_20261002.txt"
    master = (root / master_path).read_text("utf-8")
    clauses = inventory(master)
    registry = json.loads((root / "certification/master_requirement_registry.json").read_text("utf-8"))
    if registry["directive_sha256"] not in {_hash(master), _hash(master.replace("\n", "\r\n"))}:
        raise ValueError("master_directive_hash_mismatch")
    if len(clauses) != 431 or [(x["requirement_id"], x["title"], x["source"]) for x in clauses] != [
            (x["requirement_id"], x["title"], x["source"]) for x in registry["entries"]]:
        raise ValueError("master_clause_inventory_mismatch")
    for clause in clauses:
        line = int(clause["source"].rsplit(":", 1)[1])
        original = master.splitlines()[line - 1]
        identifier = master_path + "#" + clause["requirement_id"]
        entries.append({"id": identifier, "source": master_path, "source_sha256": _hash(master),
            "line_start": line, "line_end": line, "heading": clause["title"], "text": original,
            "text_sha256": _hash(original), "subrequirements": [{"id": identifier + f":L{line}", "line": line, "text": original}],
            "historical_disposition_reference": "certification/master_requirement_registry.json#" + clause["requirement_id"]})
    return entries


def validate_disposition(value: dict, entry: dict, root: Path) -> None:
    if value.get("status") not in STATUSES:
        raise ValueError("unknown_completion_status")
    if value.get("text_sha256") != entry["text_sha256"]:
        raise ValueError("stale_requirement_disposition")
    for path in value.get("canonical_paths", []):
        resolved = (root / path).resolve()
        if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
            raise ValueError("canonical_implementation_path_missing")
    if value["status"] == "BLOCKED_EXTERNAL" and not all(value.get("external", {}).get(key) for key in (
            "cause", "required_action", "retry_condition")):
        raise ValueError("external_blocker_requires_action_and_retry")
    if value["status"].startswith("VERIFIED_"):
        required = {unit["id"] for unit in entry["subrequirements"]}
        observed = set()
        evidence = value.get("evidence", [])
        for proof in evidence:
            if not all(proof.get(key) for key in ("sha", "environment", "timestamp", "command", "artifact", "result", "scope")):
                raise ValueError("incomplete_acceptance_evidence")
            if not re.fullmatch(r"[0-9a-f]{40}", proof["sha"]) or proof["result"] != "PASS":
                raise ValueError("invalid_acceptance_identity_or_result")
            if proof["scope"] != value["status"]:
                raise ValueError("acceptance_scope_mismatch")
            observed.update(proof.get("subrequirements", []))
        if observed != required or not evidence or value.get("missing_acceptance"):
            raise ValueError("full_section_acceptance_not_established")


def build(root: Path = ROOT) -> dict:
    entries = source_inventory(root)
    supplied = (root / "docs/specs/20261010/research-source-supplied.md").read_text("utf-8")
    if _hash(supplied) != "e2eb70cc274b9706def06d1b4565860c672763784cf5c72381186da12ebde333":
        raise ValueError("supplied_research_content_hash_mismatch")
    path = root / DISPOSITIONS
    dispositions = json.loads(path.read_text("utf-8")) if path.exists() else {"entries": {}}
    overrides = dispositions["entries"]
    if set(overrides) - {entry["id"] for entry in entries}:
        raise ValueError("orphan_completion_disposition")
    for entry in entries:
        disposition = overrides.get(entry["id"])
        if disposition:
            validate_disposition(disposition, entry, root)
        entry["acceptance"] = disposition or {
            "status": "AUDIT_PENDING", "current_behavior": "Source-specific runtime review remains open.",
            "canonical_paths": [], "conflicting_legacy_paths": [],
            "missing_acceptance": ["Reconcile each substantive source clause with canonical implementation and meaningful scoped acceptance."],
            "tests": {"positive": [], "negative": [], "concurrency": [], "recovery": []},
            "evidence": [], "external": None,
        }
    return {"schema_version": 1, "continuation_branch": "fix/release-recovery-20261008",
        "release_base_branch": "fix/provider-discovery-readiness-20260923", "pull_request": 189,
        "inventory_is_acceptance": False, "preserved_sections": 560, "master_clauses": 431,
        "overlapping_inventories_are_not_test_counts": True,
        "research_source": {"status": "SUPPLIED_CONTENT_REVIEW_COMPLETE",
            "sha256": "e2eb70cc274b9706def06d1b4565860c672763784cf5c72381186da12ebde333",
            "review": "docs/research-source-review-20261010.md",
            "provenance_limit": "Google Docs revision/authorship not independently authenticated.",
            "supersedes_historical": "BLOCKED_SOURCE_UNAVAILABLE"},
        "entries": entries}


def render_report(matrix: dict) -> str:
    totals = {status: sum(entry["acceptance"]["status"] == status for entry in matrix["entries"]) for status in sorted(STATUSES)}
    rows = ["# Current completion acceptance matrix", "",
        "560 preserved specification sections and 431 overlapping master clauses are retained with their exact text and substantive lines in `certification/completion_matrix.json`.", "",
        "AUDIT_PENDING means the source-specific implementation and acceptance review is unfinished. It does not mean absent functionality. Paths, test names and historical labels do not confer verification. This inventory is not a completed audit or release certificate.", "",
        "The canonical continuation is `fix/release-recovery-20261008`, PR #189; the release base remains `fix/provider-discovery-readiness-20260923`. The October 10 supplied research-content review supersedes older source-unavailable statements. Original prompts and historical reports are unchanged.", "",
        "| Status | Entries |", "| --- | ---: |"]
    rows.extend(f"| {status} | {count} |" for status, count in totals.items())
    rows.extend(["", "| Requirement | Heading | Current disposition |", "| --- | --- | --- |"])
    for entry in matrix["entries"]:
        title = entry["heading"].replace("|", "\\|").replace("\n", " ")
        label = entry["id"].split("#", 1)[1]
        rows.append(f"| [{entry['source']}#{label}](../{entry['source']}) | {title} | {entry['acceptance']['status']} |")
    rows.extend(["", "Update reviewed dispositions in `certification/completion_dispositions.json`; regenerate with `python -m scripts.completion_matrix`. `--check` detects omitted sections/clauses/subrequirements and stale or unsupported acceptance claims.", ""])
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    matrix = build()
    outputs = {OUTPUT: json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", REPORT: render_report(matrix)}
    for name, content in outputs.items():
        target = ROOT / name
        if args.check:
            if not target.exists() or target.read_text("utf-8") != content:
                raise ValueError("completion_matrix_stale:" + name)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
    print("Completion inventory: 560 preserved sections, 431 master clauses; acceptance remains separately scoped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
