from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "architecture" / "REQUIREMENTS_TRACEABILITY_MATRIX.md"
CURRENT_RELEASE = ROOT / "CURRENT_RELEASE.md"

_ALLOWED_EXTERNAL = {
    "SR-PROVIDER-008",
    "SR-SCALE-003",
    "SR-MARKETPLACE-001",
    "SR-DEMO-010",
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


def test_provider_completion_boundary_separates_enabled_from_optional_external() -> None:
    matrix = MATRIX.read_text(encoding="utf-8")
    assert "| SR-PROVIDER-007 |" in matrix
    assert "| SR-PROVIDER-007 | Every enabled/claimed market-data provider" in matrix
    provider_007 = next(cells for cells in _rows() if cells[0] == "SR-PROVIDER-007")
    provider_008 = next(cells for cells in _rows() if cells[0] == "SR-PROVIDER-008")
    assert provider_007[2] == "INTEGRATION_VERIFIED"
    assert provider_008[2] == "BLOCKED_EXTERNAL"


def test_current_release_points_to_current_release_candidate_boundary() -> None:
    text = CURRENT_RELEASE.read_text(encoding="utf-8")
    assert "Repository Alembic head: 0048_runtime_schema_bridge" in text
    assert "FINAL_COMPLETION_REPORT_20260926.md" in text
    assert "BLOCKED_EXTERNAL_REQUIREMENTS_20260926.md" in text
    assert "docs/security/THREAT_MODEL.md" in text
    assert "docs/evidence/STAGING_PROVIDER_CERTIFICATION_20260926.md" in text
    assert "NOT YET LIVE-CERTIFIED" in text
    assert "24–72 hour immutable-SHA staging soak" in text
    assert "Historical evidence retained" in text
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
