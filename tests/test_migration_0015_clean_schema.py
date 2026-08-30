from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db" / "migrations" / "versions" / "0015_active_signal_guard.py"


def test_0015_creates_signal_status_before_using_it() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS status VARCHAR(16)" in source
    assert "NOT NULL DEFAULT 'issued'" in source
    upgrade = source[source.index("def upgrade() -> None:") :]
    assert upgrade.index("_ensure_signal_status_column()") < upgrade.index(
        "_reconcile_active_duplicates()"
    )
    assert upgrade.index("_reconcile_active_duplicates()") < upgrade.index(
        "_create_indexes()"
    )


def test_0015_preserves_existing_status_values() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "UPDATE signals SET status = 'issued' WHERE status IS NULL" in source
    assert "DROP COLUMN" not in source.upper()
