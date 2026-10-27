"""Hash-checked private source intake and conservative public acceptance register.

Original wording stays in ignored local artifacts. Public rows retain stable
source anchors/hashes, never private text. Ingestion is not semantic acceptance.
Run --bundle PATH once; --check works from the sanitized index in any checkout.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
INDEX = "docs/release/crosschat_source_index.json"
DISPOSITIONS = "docs/release/crosschat_dispositions.json"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
STATUSES = {"IMPLEMENTED_AND_VERIFIED", "IMPLEMENTED_NEEDS_IMPROVEMENT", "INCOMPLETE",
            "MISSING", "BROKEN", "DUPLICATED", "SUPERSEDED", "EXTERNALLY_BLOCKED"}


def sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def source_file(bundle: Path, name: str) -> Path:
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("unsafe_source_filename")
    path = (bundle / "sources" / name).resolve()
    if not path.is_relative_to(bundle.resolve()) or not path.is_file():
        raise ValueError("source_missing_or_external")
    return path


def docx_blocks(path: Path) -> list[tuple[str, str]]:
    with ZipFile(path) as archive:
        if archive.getinfo("word/document.xml").file_size > 50_000_000:
            raise ValueError("source_document_too_large")
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find("w:body", NS)
    if body is None:
        raise ValueError("source_document_body_missing")

    def paragraph(element: ET.Element) -> str:
        values = []
        for node in element.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t":
                values.append(node.text or "")
            elif tag in {"br", "tab"}:
                values.append("\n" if tag == "br" else "\t")
        return "".join(values).strip()

    blocks = []
    for child in body:
        if child.tag == f"{{{NS['w']}}}p":
            text = paragraph(child)
            if text:
                blocks.append(("PARAGRAPH", text))
        elif child.tag == f"{{{NS['w']}}}tbl":
            for row in child.findall("w:tr", NS):
                cells = [" ".join(filter(None, (paragraph(p) for p in cell.findall("w:p", NS))))
                         for cell in row.findall("w:tc", NS)]
                text = " | ".join(cells).strip()
                if text:
                    blocks.append(("TABLE_ROW", text))
    return blocks


def ingest(bundle: Path, attachments: list[Path]) -> tuple[dict, list[dict]]:
    """Check every original block against both independent supplied exports."""
    manifest = json.loads((bundle / "indexes/manifest.json").read_text("utf-8"))
    clauses = read_csv(bundle / "indexes/source_clauses.csv")
    headings = read_csv(bundle / "indexes/source_headings.csv")
    seeds = read_csv(bundle / "indexes/known_requirements_seed.csv")
    for actual, key in ((len(clauses), "source_clause_rows"), (len(headings), "headings"),
                        (len(seeds), "historical_seed_rows")):
        if actual != manifest[key]:
            raise ValueError("source_count_mismatch:" + key)
    files, records, private, documents = [], [], [], []
    for path in sorted(bundle.rglob("*")):
        if path.is_file():
            files.append({"path": path.relative_to(bundle).as_posix(), "sha256": sha(path.read_bytes()),
                          "bytes": path.stat().st_size})
    expected_sources = {d["filename"] for d in manifest["source_documents"]}
    if {r["source"] for r in clauses} != expected_sources or {h["source"] for h in headings} != expected_sources:
        raise ValueError("unexpected_or_missing_source")
    for number, doc in enumerate(manifest["source_documents"], 1):
        original = source_file(bundle, doc["filename"])
        exported = source_file(bundle, doc["extracted_text_filename"])
        if sha(original.read_bytes()) != doc["sha256_original"] or sha(exported.read_bytes()) != doc["sha256_text"]:
            raise ValueError("original_or_export_hash_mismatch")
        rows = [r for r in clauses if r["source"] == doc["filename"]]
        if len(rows) != doc["paragraph_and_table_row_count"] or [r["block_id"] for r in rows] != [str(i) for i in range(1, len(rows)+1)]:
            raise ValueError("source_block_sequence_mismatch")
        if docx_blocks(original) != [(r["kind"], r["text"]) for r in rows]:
            raise ValueError("original_document_clause_mismatch")
        export = exported.read_text("utf-8")
        matches = list(re.finditer(r"^\[SOURCE BLOCK (\d+) \| ([^\n]*)\]\n", export, re.M))
        if len(matches) != len(rows):
            raise ValueError("export_block_count_mismatch")
        for i, (match, row) in enumerate(zip(matches, rows)):
            end = matches[i+1].start() if i+1 < len(matches) else len(export)
            if match[1] != row["block_id"] or export[match.end():end].strip() != row["text"] or sha(row["text"]) != row["sha256"]:
                raise ValueError("export_clause_or_hash_mismatch")
            identifier = f"SR-XCHAT-D{number}-B{int(row['block_id']):05d}"
            records.append({"id": identifier, "kind": "PRIVATE_SOURCE_CLAUSE", "source": f"sources/{doc['filename']}",
                            "anchor": "block:" + row["block_id"], "source_sha256": row["sha256"],
                            "source_file_sha256": doc["sha256_original"], "block_kind": row["kind"]})
            private.append({"id": identifier, **row})
        source_headings = [h for h in headings if h["source"] == doc["filename"]]
        if len(source_headings) != doc["section_heading_count"] or [h["index"] for h in source_headings] != [str(i) for i in range(1, len(source_headings)+1)]:
            raise ValueError("heading_sequence_mismatch")
        position = 0
        for heading in source_headings:
            while position < len(rows) and (rows[position]["text"], rows[position]["style"]) != (heading["heading"], heading["style"]):
                position += 1
            if position == len(rows):
                raise ValueError("heading_not_in_original_sequence")
            private.append({"kind": "HEADING", **heading, "block_id": rows[position]["block_id"]})
            position += 1
        documents.append({**doc, "original_body_matches_ledger": True, "full_export_matches_ledger": True,
                          "heading_sequence_valid": True, "semantic_review_complete": False})
    seed_ids = [r["id"] for r in seeds]
    if len(set(seed_ids)) != len(seed_ids):
        raise ValueError("duplicate_seed_id")
    for row in seeds:
        records.append({"id": row["id"], "kind": "REQUIREMENT_SEED", "source": "indexes/known_requirements_seed.csv",
                        "anchor": row["id"], "source_sha256": sha(row["original_or_summary"])})
        private.append({"kind": "REQUIREMENT_SEED", **row})
    instructions = [("bundle/"+p.name, p) for p in (bundle / "README.md", bundle / "START_HERE_MASTER_CODEX_PROMPT.md", bundle / "START_CODEX_MESSAGE.txt")]
    instructions += [(f"attachment-{i}", path) for i, path in enumerate(attachments, 1)]
    instruction_sources = []
    for name, path in instructions:
        content = path.read_text("utf-8")
        instruction_sources.append({"source": name, "sha256": sha(path.read_bytes()), "sha256_lf": sha(content),
                                    "bytes": path.stat().st_size})
        for line, text in enumerate(content.splitlines(), 1):
            if not text.strip():
                continue
            identifier = "SR-XCHAT-I-" + sha(name)[:10] + f"-L{line}"
            records.append({"id": identifier, "kind": "CURRENT_INSTRUCTION", "source": name, "anchor": f"line:{line}",
                            "source_sha256": sha(text)})
            private.append({"id": identifier, "source": name, "line": line, "text": text})
    snapshot = {"schema_version": 1, "privacy": "Original wording is private; hashes and anchors only are published.",
                "ingestion_is_acceptance": False, "files": files, "documents": documents,
                "instruction_sources": instruction_sources, "records": records,
                "counts": {"clauses": len(clauses), "headings": len(headings), "seeds": len(seeds)},
                "unavailable": [
                    {"source": "indexes/blueprint_modules.csv", "status": "SOURCE_NOT_AVAILABLE",
                     "reason": "Named by the master contract but absent from the supplied package; heading index is available."},
                    {"source": "Unsupplied ChatGPT conversation transcripts and private references", "status": "SOURCE_NOT_AVAILABLE",
                     "reason": "Bundled documents are accessible; they do not establish access to every original discussion."}],
                "scope": "All body paragraphs/table rows and supplied text/heading/seed indexes; no rendered-page or unseen-chat assertion."}
    snapshot["records_sha256"] = sha(canonical(records))
    return snapshot, private


def validate_review(review: dict, row: dict, root: Path) -> None:
    if review.get("source_sha256") != row["source_sha256"]:
        raise ValueError("stale_source_disposition")
    if review.get("status") not in STATUSES or not review.get("reviewer") or not review.get("acceptance"):
        raise ValueError("incomplete_review")
    for key in ("code", "tests", "evidence_candidates"):
        for name in review.get(key, []):
            path = (root / name.split("::", 1)[0]).resolve()
            if not path.is_relative_to(root.resolve()) or not path.exists():
                raise ValueError("missing_or_external_review_path")
    # There is no automatic upgrade from historic status, passing counts or paths.
    # Verification promotion must use the existing clause-bound receipt validator.
    if review["status"] == "IMPLEMENTED_AND_VERIFIED":
        from scripts.completion_matrix import validate_evidence_artifact
        if review.get("gaps") or not review.get("proofs"):
            raise ValueError("verification_incomplete")
        for proof in review["proofs"]:
            if not all(proof.get(key) for key in ("sha", "environment", "timestamp", "command", "artifact", "artifact_sha256", "result", "scope")):
                raise ValueError("verification_metadata_incomplete")
            if proof["scope"] not in {"VERIFIED_LOCAL", "VERIFIED_CI", "VERIFIED_STAGING"}:
                raise ValueError("verification_scope_invalid")
            if proof.get("result") != "PASS" or not re.fullmatch(r"[0-9a-f]{40}", proof.get("sha", "")) or proof.get("subrequirements") != [row["id"]]:
                raise ValueError("verification_scope_incomplete")
            validate_evidence_artifact(proof, {"text_sha256": row["source_sha256"]}, root)
    if review["status"] == "EXTERNALLY_BLOCKED" and not all(review.get("external", {}).get(k) for k in ("owner", "action", "retry_condition")):
        raise ValueError("external_blocker_incomplete")
    if review["status"] in {"DUPLICATED", "SUPERSEDED"} and not review.get("resolved_by"):
        raise ValueError("disposition_requires_precedence_target")


def build(snapshot: dict, inventory: dict, reviews: dict, root: Path = ROOT) -> tuple[list[dict], dict]:
    if snapshot["records_sha256"] != sha(canonical(snapshot["records"])):
        raise ValueError("source_index_integrity_mismatch")
    rows = []
    for item in snapshot["records"]:
        rows.append({**item, "status": "INCOMPLETE", "applicability": "UNREVIEWED", "acceptance": None,
                     "code": [], "tests": [], "runtime_proof": [], "reviewer": None,
                     "owner": "Source reconciliation", "impact": "UNASSESSED", "dependencies": [],
                     "gap": "Clause-specific implementation and acceptance reconciliation is unfinished; no absence or defect inferred."})
    for item in inventory["requirements"] + inventory["interfaces"]:
        rows.append({"id": item["id"], "kind": "REPOSITORY_" + item["kind"], "source": item["source"],
                     "source_sha256": sha(canonical(item)), "source_reference": "docs/release/requirements.json#" + item["id"],
                     "status": "INCOMPLETE", "applicability": "UNREVIEWED", "acceptance": None,
                     "code": [], "tests": [], "runtime_proof": [], "reviewer": None,
                     "owner": item["responsible_component"], "impact": "UNASSESSED", "dependencies": [],
                     "prior_status": item["status"], "owner_candidate": item["responsible_component"],
                     "gap": "Retained source/code/evidence mappings require current clause-specific review.",
                     "retained_child_clause_count": len(item.get("clauses", item.get("subrequirements", [])))})
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids) or set(reviews) - set(ids):
        raise ValueError("duplicate_id_or_orphan_review")
    for row in rows:
        if row["id"] in reviews:
            review = reviews[row["id"]]
            validate_review(review, row, root)
            row.update(review)
            row["applicability"] = "APPLICABLE" if row["status"] not in {"DUPLICATED", "SUPERSEDED"} else "RESOLVED_BY_PRECEDENCE"
            row.pop("gap", None)
    pending = sum(r["applicability"] == "UNREVIEWED" for r in rows)
    counts = dict(sorted(Counter(r["status"] for r in rows).items()))
    coverage = {"schema_version": 1, "release_decision": "NO-GO", "ingestion_is_acceptance": False,
                "source_index_sha256": sha(canonical(snapshot)), "repository_inventory_sha256": sha(canonical(inventory)),
                "sources": snapshot["documents"], "bundle_counts": snapshot["counts"], "unavailable": snapshot["unavailable"],
                "register_rows": len(rows), "status_counts": counts, "reviewed_rows": len(reviews),
                "unclassified_applicable": pending, "unclassified_count_scope": "Conservative upper bound: includes all unresolved applicability reviews, including headings/context.",
                "applicable_reviewed": sum(r["applicability"] == "APPLICABLE" for r in rows),
                "irrelevant_boilerplate_reviewed": 0, "implemented_and_verified": counts.get("IMPLEMENTED_AND_VERIFIED", 0),
                "repository_retained_child_clauses": sum(r.get("retained_child_clause_count", 0) for r in rows),
                "limitations": ["Repository rows retain their complete child clauses through the existing register; these are not yet individually dispositioned.",
                                "Private original wording remains retrievable by source anchor/hash in the supplied bundle and ignored local intake.",
                                "An exact repeated text hash does not prove semantic duplication or supersession."]}
    return rows, coverage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--attachment", type=Path, action="append", default=[])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.bundle:
        snapshot, private = ingest(args.bundle, args.attachment)
        if args.check:
            if json.loads((ROOT / INDEX).read_text("utf-8")) != snapshot:
                raise ValueError("private_intake_index_stale")
        else:
            (ROOT / INDEX).write_text(json.dumps(snapshot, indent=2)+"\n", encoding="utf-8", newline="\n")
            target = ROOT / "artifacts/crosschat-private/full_sources.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("".join(canonical(r)+"\n" for r in private), encoding="utf-8", newline="\n")
    else:
        snapshot = json.loads((ROOT / INDEX).read_text("utf-8"))
    inventory = json.loads((ROOT / "docs/release/requirements.json").read_text("utf-8"))
    reviews = json.loads((ROOT / DISPOSITIONS).read_text("utf-8"))["entries"]
    rows, coverage = build(snapshot, inventory, reviews)
    report = ["# Cross-chat requirement register", "", "NO-GO. Source ingestion is not implementation or verification.", "",
              "Private source wording is deliberately omitted. Use each source anchor/hash with the local bundle; repository details remain in requirements.json.", "",
              f"Rows: {len(rows)}. Reviewed dispositions: {len(reviews)}. Unresolved applicability/acceptance: {coverage['unclassified_applicable']}.", "",
              "| Requirement | Source anchor | Status |", "| --- | --- | --- |"]
    report += [f"| {r['id']} | {r['source'].replace('|', '/')} {r.get('anchor', '')} | {r['status']} |" for r in rows]
    outputs = {"docs/release/requirements_universe.jsonl": "".join(canonical(r)+"\n" for r in rows),
               "docs/release/source_coverage.json": json.dumps(coverage, indent=2)+"\n",
               "docs/release/CROSSCHAT_REQUIREMENTS_MATRIX.md": "\n".join(report)+"\n"}
    for name, content in outputs.items():
        target = ROOT / name
        if args.check:
            if not target.exists() or target.read_text("utf-8") != content:
                raise ValueError("crosschat_register_stale:" + name)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
    print(canonical({"rows": len(rows), "bundle_counts": snapshot["counts"], "reviewed": len(reviews),
                     "unclassified_applicable": coverage["unclassified_applicable"], "release_decision": "NO-GO"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
