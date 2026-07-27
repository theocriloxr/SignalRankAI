from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from signalrank_telegram import callback_handlers as callbacks


def _fixture():
    query = SimpleNamespace(
        answer=AsyncMock(),
        data="",
        from_user=SimpleNamespace(id=1234),
        message=SimpleNamespace(chat_id=9876, message_id=42),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=1234),
    )
    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock())
    context = SimpleNamespace(bot=bot)
    return update, context, query, bot


@pytest.mark.asyncio
async def test_signal_chart_callback_renders_authorized_delivery(monkeypatch):
    update, context, query, bot = _fixture()
    signal = {"signal_id": "sig-1", "asset": "BTCUSDT", "timeframe": "1h", "direction": "long"}
    monkeypatch.setattr(callbacks, "_load_authorized_signal_payload", AsyncMock(return_value=signal))

    image = BytesIO(b"png")
    image.name = "sig-1.png"
    from signalrank_telegram import signal_charts

    monkeypatch.setattr(signal_charts, "build_signal_chart", AsyncMock(return_value=image))

    await callbacks._handle_signal_chart(update, context, "sig-1")

    query.answer.assert_awaited()
    bot.send_photo.assert_awaited_once()
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["chat_id"] == 9876
    assert kwargs["photo"] is image
    assert "BTCUSDT" in kwargs["caption"]
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_signal_chart_callback_rejects_forged_or_undelivered_signal(monkeypatch):
    update, context, _query, bot = _fixture()
    monkeypatch.setattr(callbacks, "_load_authorized_signal_payload", AsyncMock(return_value=None))

    await callbacks._handle_signal_chart(update, context, "foreign-signal")

    bot.send_photo.assert_not_awaited()
    bot.send_message.assert_awaited_once()
    assert "not delivered to your account" in bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_gemini_callback_returns_real_advisory_output(monkeypatch):
    update, context, query, bot = _fixture()
    signal = {"signal_id": "sig-2", "asset": "EURUSD", "direction": "short"}
    monkeypatch.setattr(callbacks, "_load_authorized_signal_payload", AsyncMock(return_value=signal))

    from services import gemini_ml

    reviewer = AsyncMock(return_value="Momentum and regime gates support the setup.")
    monkeypatch.setattr(gemini_ml, "ask_gemini_signal_explanation", reviewer)

    await callbacks._handle_ask_gemini(update, context, "sig-2")

    query.answer.assert_awaited()
    reviewer.assert_awaited_once()
    bot.send_message.assert_awaited_once()
    assert "Gemini advisory review" in bot.send_message.await_args.kwargs["text"]
    assert "Momentum" in bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_gemini_callback_degrades_without_claiming_success(monkeypatch):
    update, context, _query, bot = _fixture()
    monkeypatch.setattr(
        callbacks,
        "_load_authorized_signal_payload",
        AsyncMock(return_value={"signal_id": "sig-3", "asset": "SOLUSDT"}),
    )

    from services import gemini_ml

    monkeypatch.setattr(gemini_ml, "ask_gemini_signal_explanation", AsyncMock(return_value=None))

    await callbacks._handle_ask_gemini(update, context, "sig-3")

    text = bot.send_message.await_args.kwargs["text"]
    assert "currently unavailable" in text
    assert "deterministic signal" in text


def test_no_visible_callback_or_filter_placeholder_remains():
    callback_source = callbacks.__file__
    bot_source = __import__("signalrank_telegram.bot", fromlist=["__file__"]).__file__
    callback_text = open(callback_source, encoding="utf-8").read().lower()
    bot_text = open(bot_source, encoding="utf-8").read().lower()

    assert "chart view is not available yet" not in callback_text
    assert "gemini analysis is being prepared" not in callback_text
    assert "opening mt5 trade execution" not in callback_text
    assert "_filter_placeholder" not in bot_text
