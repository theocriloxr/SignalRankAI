from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_0036_notification_preferences_backfill_does_not_depend_on_users_timezone() -> None:
    source = (
        ROOT / "db" / "migrations" / "versions" / "0036_unified_platform_identity.py"
    ).read_text(encoding="utf-8")
    block = source[
        source.index("INSERT INTO notification_preferences"):
        source.index("def downgrade()")
    ]
    assert "COALESCE(timezone" not in block
    assert "SELECT id, CASE WHEN telegram_user_id IS NULL THEN FALSE ELSE TRUE END," in block
    assert "'UTC'" in block
    assert "FROM users" in block


def test_0036_creates_notification_timezone_before_backfill() -> None:
    source = (
        ROOT / "db" / "migrations" / "versions" / "0036_unified_platform_identity.py"
    ).read_text(encoding="utf-8")
    create_pos = source.index("CREATE TABLE IF NOT EXISTS notification_preferences")
    timezone_pos = source.index("timezone VARCHAR(64) NOT NULL DEFAULT 'UTC'", create_pos)
    backfill_pos = source.index("INSERT INTO notification_preferences", timezone_pos)
    assert create_pos < timezone_pos < backfill_pos
