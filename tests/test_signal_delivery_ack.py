from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_fresh_signal_returns_telegram_ack(monkeypatch):
    import engine.delivery_freshness as freshness_module
    import signalrank_telegram.bot as bot_module

    observed = {}

    async def _fresh(*_args, **_kwargs):
        observed.update(_kwargs)
        return SimpleNamespace(
            ok=True,
            live_price=100.1,
            opportunity_remaining_pct=92.0,
        )

    async def _no_edit(*_args, **_kwargs):
        return None

    async def _unlocked(*_args, **_kwargs):
        return False

    async def _send(*_args, **_kwargs):
        return SimpleNamespace(message_id=77, chat=SimpleNamespace(id=1234))

    async def _phase(**_kwargs):
        return True

    async def _stash(_receipt):
        return True

    monkeypatch.setattr(freshness_module, "validate_delivery_freshness", _fresh)
    monkeypatch.setattr(bot_module, "format_signal", lambda *_args, **_kwargs: "signal")
    monkeypatch.setattr(bot_module, "_find_editable_signal_message", _no_edit)
    monkeypatch.setattr(bot_module, "_is_asset_delivery_locked", _unlocked)
    monkeypatch.setattr(bot_module, "_send_signal_with_engagement_async", _send)
    monkeypatch.setattr(bot_module, "_persist_delivery_phase", _phase)
    monkeypatch.setattr("delivery.receipts.receipt_store.stash", _stash)

    proof = await bot_module._deliver_or_update_signal_async(
        bot=SimpleNamespace(),
        telegram_user_id=1234,
        signal={"signal_id": "sig-1", "asset": "BTCUSDT", "timeframe": "5m"},
        display_tier="premium",
    )

    assert proof["mode"] == "sent"
    assert proof["chat_id"] == 1234
    assert proof["message_id"] == 77
    assert proof["receipt_stashed"] is True
    assert proof["delivery_receipt"]["idempotency_key"]
    assert observed["final_send"] is True
    assert observed["delivery_tier"] == "premium"
    assert "cached_live_price" not in observed


@pytest.mark.asyncio
async def test_signal_without_telegram_message_id_cannot_be_confirmed(monkeypatch):
    import engine.delivery_freshness as freshness_module
    import signalrank_telegram.bot as bot_module

    async def _fresh(*_args, **_kwargs):
        return SimpleNamespace(ok=True, live_price=None, opportunity_remaining_pct=100.0)

    async def _none(*_args, **_kwargs):
        return None

    async def _unlocked(*_args, **_kwargs):
        return False

    async def _send(*_args, **_kwargs):
        return SimpleNamespace(message_id=None, chat=SimpleNamespace(id=1234))

    async def _phase(**_kwargs):
        return True

    monkeypatch.setattr(freshness_module, "validate_delivery_freshness", _fresh)
    monkeypatch.setattr(bot_module, "format_signal", lambda *_args, **_kwargs: "signal")
    monkeypatch.setattr(bot_module, "_find_editable_signal_message", _none)
    monkeypatch.setattr(bot_module, "_is_asset_delivery_locked", _unlocked)
    monkeypatch.setattr(bot_module, "_send_signal_with_engagement_async", _send)
    monkeypatch.setattr(bot_module, "_persist_delivery_phase", _phase)

    with pytest.raises((TypeError, ValueError)):
        await bot_module._deliver_or_update_signal_async(
            bot=SimpleNamespace(),
            telegram_user_id=1234,
            signal={"signal_id": "sig-2", "asset": "ETHUSDT", "timeframe": "5m"},
            display_tier="premium",
        )


def test_gemini_recommendations_are_normalized():
    from services.gemini_ml import _review_feature_suggestions

    analysis = """ASSESSMENT: Stable\nPATTERNS: Low coverage\nRECOMMENDATIONS:\n- Raise coverage\n- Audit TP1"""

    assert _review_feature_suggestions(analysis) == ["Raise coverage", "Audit TP1"]
