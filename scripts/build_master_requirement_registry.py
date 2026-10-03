"""Inventory every actionable clause in the user's frozen master directive.

This inventories requirements, not implementation completion. Existing evidence
is preserved by stable ID; inventory alone can never grant VERIFIED status.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/SIGNALRANKAI_MASTER_DIRECTIVE_20261002.txt"
OUTPUT = ROOT / "certification/master_requirement_registry.json"
STATUSES = ["IMPLEMENTED_VERIFIED", "IMPLEMENTED_UNVERIFIED", "PARTIAL", "BLOCKED_EXTERNAL",
            "FAILED", "DEFERRED", "NOT_APPLICABLE"]


def inventory(text: str) -> list[dict]:
    entries = []
    section = "preamble"
    ordinals: dict[str, int] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        appendix = re.match(r"^Appendix ([A-C])\.", line)
        if appendix:
            section = f"appendix-{appendix.group(1)}"
            continue
        heading = re.match(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][^\t]+)$", line)
        if heading:
            section = heading.group(1)
            continue
        explicit = re.match(r"^(P0-SIG-\d{3}|G\d{2})\s+(.+)$", line)
        route = re.match(r"^(/(?:app)?[^\s]*)\s+(.+)$", line) if section == "16" else None
        is_checkbox = line.startswith("\u2610") or (section == "appendix-C" and line.startswith("\u2022"))
        is_loop_step = section in {"1.1", "22"} and bool(re.match(r"^\d+[.)]\s", line))
        is_policy = line.startswith(("FINAL RULE:", "LIVE-TRADING MEANING:", "VERDICT POLICY:", "ONLY STOP WHEN:"))
        if not (explicit or route or is_checkbox or is_loop_step or is_policy):
            continue
        ordinals[section] = ordinals.get(section, 0) + 1
        requirement_id = explicit.group(1) if explicit else f"SR-MASTER-{section.replace('.', '-')}-{ordinals[section]:03d}"
        title = explicit.group(2) if explicit else line.removeprefix("\u2610").removeprefix("\u2022").strip()
        entries.append({
            "requirement_id": requirement_id,
            "title": title,
            "source": f"docs/SIGNALRANKAI_MASTER_DIRECTIVE_20261002.txt:{lineno}",
            "section": section,
            "severity": "P0" if requirement_id.startswith("P0-") or is_policy else "P1",
            "status": "PARTIAL",
            "code_evidence": [], "test_evidence": [], "runtime_evidence": [],
            "staging_evidence": [], "production_evidence": [],
            "blocker": "Audit pending; this inventory makes no implementation or verification claim.",
            "last_verified_sha": None, "last_verified_at": None, "regression_link": None,
        })
    return entries


def build() -> dict:
    raw = SOURCE.read_bytes()
    entries = inventory(raw.decode("utf-8"))
    previous = json.loads(OUTPUT.read_text("utf-8")) if OUTPUT.exists() else {}
    old = {entry["requirement_id"]: entry for entry in previous.get("entries", [])}
    for entry in entries:
        historical = old.get(entry["requirement_id"])
        if historical and historical["title"] == entry["title"]:
            entry.update(historical)
    ids = [entry["requirement_id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_master_requirement_id")
    if not {f"G{index:02d}" for index in range(1, 33)}.issubset(ids):
        raise ValueError("master_release_gate_inventory_incomplete")
    return {
        "schema_version": "1.0", "release_branch": "implementation-of-master-blueprint",
        "directive_sha256": hashlib.sha256(raw).hexdigest(), "statuses": STATUSES,
        "live_readiness_verdict": "NO / NOT YET",
        "inventory_is_verification": False, "entries": entries,
        "audit_discoveries": previous.get("audit_discoveries", []),
    }


if __name__ == "__main__":
    result = build()
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"master_requirements={len(result['entries'])} live_readiness=NO/NOT_YET")
