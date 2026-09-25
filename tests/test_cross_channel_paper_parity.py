from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cross_channel_paper_receipts_are_the_single_migration_head() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "db" / "migrations"))
    assert ScriptDirectory.from_config(cfg).get_heads() == [
        "0040_cross_channel_paper_receipt"
    ]
    migration = _source(
        "db/migrations/versions/0040_cross_channel_paper_receipts.py"
    )
    assert 'down_revision = "0039_web_signup_acquisition"' in migration
    assert len("0040_cross_channel_paper_receipt") <= 32
    assert "ALTER COLUMN delivery_id DROP NOT NULL" in migration
    assert "ADD COLUMN IF NOT EXISTS receipt_channel" in migration
    assert "ADD COLUMN IF NOT EXISTS receipt_reference" in migration


def test_paper_attempt_model_preserves_channel_neutral_provenance() -> None:
    models = _source("db/models.py")
    start = models.index("class PaperTradeAttempt")
    end = models.index("class PerformanceLedgerEntry", start)
    block = models[start:end]
    assert "Mapped[Optional[int]]" in block
    assert 'receipt_channel: Mapped[str]' in block
    assert 'receipt_reference: Mapped[Optional[str]]' in block


def test_paper_service_supports_web_receipts_without_fake_telegram_delivery() -> None:
    service = _source("core/paper_trading_service.py")
    assert "async def _web_delivery_candidates(" in service
    assert '"receipt_channel": "web"' in service
    assert '"delivery_id": None' in service
    assert "notification_events ne" in service
    assert "get_platform_execution_evidence" in service
    assert "get_platform_user_trading_preferences" in service
    assert "await self._ensure_account_for_user(session, user)" in service
    assert "web_signal_receipt" in service
    assert "INSERT INTO signal_deliveries" not in service


def test_paper_service_keeps_strict_telegram_candidate_proof() -> None:
    service = _source("core/paper_trading_service.py")
    block = service[
        service.index("async def _telegram_delivery_candidates"):
        service.index("async def _web_delivery_candidates")
    ]
    assert "SignalDelivery.sent_ok.is_(True)" in block
    assert "SignalDelivery.telegram_chat_id.is_not(None)" in block
    assert "SignalDelivery.telegram_message_id.is_not(None)" in block
    assert "SignalDelivery.delivery_confirmed_at.is_not(None)" in block
    assert '"receipt_channel": "telegram"' in block


def test_paper_worker_merges_receipts_by_canonical_user_and_signal() -> None:
    service = _source("core/paper_trading_service.py")
    block = service[
        service.index("async def _delivery_candidates"):
        service.index("async def process_new_deliveries")
    ]
    assert "self._telegram_delivery_candidates(batch)" in block
    assert "self._web_delivery_candidates(batch)" in block
    assert 'int(candidate["user_id"])' in block
    assert 'str(candidate["signal_id"])' in block
    assert "for candidate in [*web_rows, *telegram_rows]" in block


def test_paper_attempts_and_positions_allow_web_receipt_provenance() -> None:
    service = _source("core/paper_trading_service.py")
    assert "receipt_channel=receipt_channel" in service
    assert "receipt_reference=receipt_reference[:64] or None" in service
    assert "if candidate.get(\"delivery_id\") is not None" in service
    assert "paper:{receipt_channel}:{receipt_reference}" in service
    assert '"receipt_channel": candidate.get("receipt_channel") or "telegram"' in service


def test_web_paper_controls_use_canonical_platform_identity() -> None:
    api = _source("web/platform_api.py")
    start = api.index("def _paper_snapshot_dict")
    end = api.index('@router.get("/instruments/search")', start)
    block = api[start:end]
    assert "_telegram_identity_or_409" not in block
    assert 'user_identity="platform"' in block
    assert '_assert_feature(user, "paper_trading")' in block
    assert '"user_id": int(snapshot.user_id)' in block
    assert '"identity": str(snapshot.identity)' in block


def test_web_paper_notifications_are_idempotent_and_preference_scoped() -> None:
    service = _source("core/paper_trading_service.py")
    block = service[
        service.index("async def _notify_paper_decision"):
        service.index("async def _open_candidate(")
    ]
    assert "signalrank:web-paper:" in block
    assert "ON CONFLICT(notification_id) DO NOTHING" in block
    assert "COALESCE(np.web_enabled,TRUE) IS TRUE" in block
    assert "COALESCE(u.is_blocked,FALSE) IS FALSE" in block
    assert "'paper_trade'" in block


def test_platform_signal_reference_accepts_web_proof_without_weakening_message_links() -> None:
    resolver = _source("db/signal_reference.py")
    assert "canonical_user_id: int | None = None" in resolver
    assert "identity = \"platform\"" in resolver
    assert "notification_events" in resolver
    assert "SignalDelivery.telegram_message_id == int(message_id)" in resolver
    assert "SignalDelivery.sent_ok.is_(True)" in resolver


def test_professional_signal_feed_uses_current_schema_and_cross_channel_receipts() -> None:
    api = _source("web/platform_api.py")
    block = api[
        api.index('@router.get("/professional/signals")'):
        api.index('@router.get("/webhooks")')
    ]
    assert "s.signal_id" in block
    assert "s.take_profit" in block
    assert "sd.delivered_at" in block
    assert "notification_events" in block
    assert "_present_signal_for_tier" in block
    assert "s.id AS signal_id" not in block
    assert "s.tp1" not in block
    assert "d.sent_at" not in block



def test_web_paper_ui_no_longer_requires_telegram_link() -> None:
    js = _source("web/platform_app/app.js")
    assert "Telegram link required for automatic paper controls." not in js
    assert "Link Telegram to access delivery-proven paper history" not in js
    assert "Your account does not need Telegram to use web paper trading." in js
    assert "receipt_channel||'account'" in js


def test_platform_paper_retry_uses_canonical_web_receipt_when_needed() -> None:
    service = _source("core/paper_trading_service.py")
    block = service[
        service.index("async def request_retry"):
        service.index("async def _open_position_snapshots")
    ]
    assert 'canonical_user_id=int(user_id)' in block
    assert "notification_events" in block
    assert '"receipt_channel": receipt_channel' in block
    assert '"delivery_id": delivery_id' in block
    assert 'user_identity=identity' in block


def test_all_web_paper_account_operations_use_platform_identity() -> None:
    api = _source("web/platform_api.py")
    block = api[
        api.index('@router.get("/paper/detail")'):
        api.index('@router.get("/instruments/search")')
    ]
    assert block.count('user_identity="platform"') >= 8
    assert "_telegram_identity_or_409" not in api
