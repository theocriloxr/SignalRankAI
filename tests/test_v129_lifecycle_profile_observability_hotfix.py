from __future__ import annotations

import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v129_version_and_fingerprint() -> None:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT

    assert APP_VERSION == "1.3.5"
    assert RELEASE_FINGERPRINT == "v1.3.5-ml-learning-runtime-reliability-20260802"


def test_lifecycle_event_imports_func_in_its_own_scope() -> None:
    from engine.signal_lifecycle import record_lifecycle_event

    source = inspect.getsource(record_lifecycle_event)
    assert "from sqlalchemy import func, select" in source
    assert "func.lower(SignalDelivery.delivery_state)" in source


def test_profile_releases_db_before_telegram_and_reuses_loaded_timezone_user() -> None:
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    start = source.index("async def profile_command")
    end = source.index("async def mission_command", start)
    block = source[start:end]
    assert 'label="profile.read" if is_read else "profile.write"' in block
    assert "timeout_seconds=5" in block
    session_end = block.index("\n\t\tawait update.message.reply_text")
    session_start = block.index("async with get_session")
    assert session_end > session_start
    assert "maybe_prompt_timezone(update.message, user_id, user=timezone_user)" in block
    assert block.index("maybe_prompt_timezone(update.message, user_id, user=timezone_user)") > session_end


def test_timezone_prompt_can_skip_nested_db_lookup() -> None:
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    start = source.index("async def maybe_prompt_timezone")
    end = source.index("async def handle_timezone_callback", start)
    block = source[start:end]
    assert "*, user=None" in block
    assert "if user is None:" in block
    assert "user = await _get_timezone_user" in block


def test_ops_health_uses_main_pool_inventory_fallback() -> None:
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    start = source.index("async def ops_health_command")
    end = source.index("from .user_prefs", start)
    block = source[start:end]
    assert 'pool.get("engine_inventory")' in block
    assert 'not item.get("nullpool")' in block
    session_source = (ROOT / "db" / "session.py").read_text(encoding="utf-8")
    assert 'label="db.health", timeout_seconds=3' in session_source


def test_v129_profiles_exist_and_raise_interactive_gate_timeout() -> None:
    for name in (
        "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example",
        "SignalRankAI_v1.3.2_Railway_Full_System_Live_Paystack_Staging.env.example",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "APP_VERSION=1.3.2" in text
        assert "DB_INTERACTIVE_SESSION_GATE_TIMEOUT_SECONDS=3" in text


def test_bot_ready_notification_is_cross_instance_deduplicated() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    start = source.index("async def _notify_admin_bot_ready")
    end = source.index("async def _maybe_startup_delay", start)
    block = source[start:end]
    assert "BOT_READY_NOTIFICATION_DEDUPE_SECONDS" in block
    assert "nx=True" in block
    assert "duplicate suppressed" in block
