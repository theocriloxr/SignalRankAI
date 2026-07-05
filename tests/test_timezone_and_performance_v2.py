from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def test_timezone_aliases_and_iana_names_resolve():
    from signalrank_telegram.timezones import resolve_timezone_query

    assert resolve_timezone_query("Lagos") == "Africa/Lagos"
    assert resolve_timezone_query("New York") == "America/New_York"
    assert resolve_timezone_query("Asia/Tokyo") == "Asia/Tokyo"
    assert resolve_timezone_query("Not/A_Real_Zone") is None


def test_location_coordinates_are_private_by_default(monkeypatch):
    from signalrank_telegram.timezones import should_store_location_coordinates

    monkeypatch.delenv("TIMEZONE_STORE_LOCATION_COORDINATES", raising=False)
    assert should_store_location_coordinates() is False
    monkeypatch.setenv("TIMEZONE_STORE_LOCATION_COORDINATES", "1")
    assert should_store_location_coordinates() is True


def test_travel_mode_refresh_is_due_only_for_stale_auto_users():
    from signalrank_telegram.timezones import travel_timezone_refresh_due

    now = datetime.now(timezone.utc)
    fixed = SimpleNamespace(timezone_auto_update=False, timezone_updated_at=now - timedelta(days=30))
    fresh = SimpleNamespace(timezone_auto_update=True, timezone_updated_at=now - timedelta(days=2))
    stale = SimpleNamespace(timezone_auto_update=True, timezone_updated_at=now - timedelta(days=15))
    assert travel_timezone_refresh_due(fixed, days=14) is False
    assert travel_timezone_refresh_due(fresh, days=14) is False
    assert travel_timezone_refresh_due(stale, days=14) is True


def test_timezone_display_feature_flag_forces_utc(monkeypatch):
    from signalrank_telegram.timezones import format_user_datetime

    monkeypatch.setenv("SIGNAL_TIMEZONE_DISPLAY_ENABLED", "0")
    value = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    rendered = format_user_datetime(value, "Africa/Lagos")
    assert "12:00 PM UTC" in rendered


def test_timezone_handlers_and_settings_navigation_are_registered():
    bot = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    commands = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    utils = (ROOT / "signalrank_telegram" / "utils.py").read_text(encoding="utf-8")

    assert 'CommandHandler("timezone"' in bot
    assert 'CommandHandler("travelmode"' in bot
    assert 'CommandHandler("settings"' in bot
    assert 'filters.Regex(r"^Keep UTC$")' in bot
    assert 'callback_data="nav_settings"' in commands
    assert 'callback_data="nav_settings"' in utils
    assert 'data == "nav_settings"' in commands


def test_timezone_migration_and_performance_v2_contracts():
    migration = (ROOT / "db" / "migrations" / "versions" / "0019_user_timezone_privacy.py").read_text(encoding="utf-8")
    pg_features = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    commands = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")

    assert 'down_revision = "0018_signal_lifecycle_events"' in migration
    assert "timezone_auto_update" in migration
    assert "performance_version" in migration
    assert "COALESCE(s.performance_version, 1) >= :performance_version" in pg_features
    assert "COALESCE(s.performance_version, 1) >= :performance_version" in commands
