from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "architecture" / "REQUIREMENTS_TRACEABILITY_MATRIX.md"
CURRENT_RELEASE = ROOT / "CURRENT_RELEASE.md"

_ALLOWED_EXTERNAL = {
    "SR-PROVIDER-007",
    "SR-SCALE-003",
    "SR-ORDER-002",
}


def _rows() -> list[list[str]]:
    rows: list[list[str]] = []
    for raw in MATRIX.read_text(encoding="utf-8").splitlines():
        if not raw.startswith("| SR-"):
            continue
        cells = [cell.strip() for cell in raw.split("|")[1:-1]]
        if len(cells) >= 3:
            rows.append(cells)
    return rows


def test_traceability_has_no_internal_unfinished_statuses() -> None:
    forbidden = {"NOT_STARTED", "IMPLEMENTED_UNTESTED", "IN_PROGRESS"}
    stale: list[tuple[str, str]] = []
    for cells in _rows():
        requirement_id, status = cells[0], cells[2]
        if status in forbidden:
            stale.append((requirement_id, status))
    assert stale == []


def test_only_deliberate_external_requirements_remain_blocked() -> None:
    blocked = {
        cells[0]
        for cells in _rows()
        if cells[2] == "BLOCKED_EXTERNAL"
    }
    assert blocked == _ALLOWED_EXTERNAL


def test_current_release_points_to_current_0045_boundary() -> None:
    text = CURRENT_RELEASE.read_text(encoding="utf-8")
    assert "Repository Alembic head: 0045_mt5_credential_retirement" in text
    assert "FINAL_COMPLETION_REPORT_20260926.md" in text
    assert "BLOCKED_EXTERNAL_REQUIREMENTS_20260926.md" in text
    assert "docs/security/THREAT_MODEL.md" in text
    assert "Older R4/v1.5.1 reports remain historical evidence" in text
    assert "See `STAGING_COMPLETION_R4.md`" not in text


def test_supply_chain_provenance_is_part_of_current_security_contract() -> None:
    matrix = MATRIX.read_text(encoding="utf-8")
    threat = (ROOT / "docs" / "security" / "THREAT_MODEL.md").read_text(
        encoding="utf-8"
    )
    assert "SR-SEC-005" in matrix
    assert "CycloneDX" in matrix
    assert "scripts/generate_release_provenance.py" in matrix
    assert "deterministic CycloneDX SBOM" in threat
    assert "external artifact signing/key custody remains separate" in threat
