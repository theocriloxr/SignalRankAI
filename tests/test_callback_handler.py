import asyncio
import types
import importlib

import pytest


class DummyUser:
    def __init__(self, id):
        self.id = id


class DummyMessage:
    def __init__(self, chat_id=12345, message_id=111):
        class Chat:
            def __init__(self, id):
                self.id = id

        self.chat = Chat(chat_id)
        self.chat_id = chat_id
        self.message_id = message_id


class DummyCallbackQuery:
    def __init__(self, data, user_id=999, chat_id=12345, message_id=111):
        self.data = data
        self.from_user = DummyUser(user_id)
        self.message = DummyMessage(chat_id=chat_id, message_id=message_id)
        self.answered = False

    async def answer(self, *args, **kwargs):
        # emulate telegram CallbackQuery.answer()
        self.answered = True


class DummyUpdate:
    def __init__(self, cq: DummyCallbackQuery):
        self.callback_query = cq
        self.effective_user = cq.from_user


class DummyContext:
    def __init__(self):
        self.bot = types.SimpleNamespace()


def _keyboard_callback_payloads(keyboard):
    payloads = []
    for row in getattr(keyboard, "inline_keyboard", []) or []:
        for button in row:
            payload = getattr(button, "callback_data", None)
            if payload:
                payloads.append(payload)
    return payloads


def test_signal_keyboards_use_telegram_safe_callback_data():
    from signalrank_telegram.bot import _build_monitor_keyboard, _build_signal_keyboard
    from signalrank_telegram.commands import _build_signal_action_keyboard
    from signalrank_telegram.utils import _build_signal_action_keyboard as _build_utils_signal_action_keyboard

    long_signal_id = "12345678-1234-1234-1234-123456789abc-extra-payload-that-would-break-telegram"
    keyboards = [
        _build_signal_keyboard(long_signal_id),
        _build_monitor_keyboard(long_signal_id),
        _build_signal_action_keyboard({"signal_id": long_signal_id, "asset": "BTCUSDT"}),
        _build_utils_signal_action_keyboard({"signal_id": long_signal_id, "asset": "BTCUSDT"}),
    ]

    allowed_prefixes = (
        "mt5_trade_",
        "signal_reaction_",
        "monitor_signal_",
        "check_outcome_",
    )
    for keyboard in keyboards:
        payloads = _keyboard_callback_payloads(keyboard)
        assert payloads
        for payload in payloads:
            assert len(payload.encode("utf-8")) <= 64
            assert payload.startswith(allowed_prefixes)
            assert "extra-payload" not in payload


def test_global_callback_handler_routing(monkeypatch):
    async def _runner():
        mod = importlib.import_module("signalrank_telegram.callback_handlers")

        calls = []

        def make_stub(name):
            async def _stub(update, context, *args, **kwargs):
                calls.append((name, args, kwargs))

            return _stub

        # Patch all specific handlers so the test is isolated from DB and other IO
        monkeypatch.setattr(mod, "_handle_mt5_trade", make_stub("mt5_trade"))
        monkeypatch.setattr(mod, "_handle_signal_reaction", make_stub("signal_reaction"))
        monkeypatch.setattr(mod, "_handle_monitor_signal", make_stub("monitor_signal"))
        monkeypatch.setattr(mod, "_handle_check_outcome", make_stub("check_outcome"))
        monkeypatch.setattr("signalrank_telegram.commands.mt5_status_command", make_stub("mt5_status"))
        monkeypatch.setattr(mod, "_handle_default_callback", make_stub("default"))

        ctx = DummyContext()

        # Test mt5_trade routing
        cq = DummyCallbackQuery("mt5_trade_ABC123", user_id=42)
        upd = DummyUpdate(cq)
        await mod._global_callback_handler(upd, ctx)
        assert any(c[0] == "mt5_trade" for c in calls)

        # Test signal_reaction routing (signal_id|reaction)
        cq2 = DummyCallbackQuery("signal_reaction_SIG1|taking_it", user_id=43)
        upd2 = DummyUpdate(cq2)
        await mod._global_callback_handler(upd2, ctx)
        assert any(c[0] == "signal_reaction" for c in calls)

        # Test monitor_signal routing
        cq3 = DummyCallbackQuery("monitor_signal_SIG2", user_id=44)
        upd3 = DummyUpdate(cq3)
        await mod._global_callback_handler(upd3, ctx)
        assert any(c[0] == "monitor_signal" for c in calls)

        # Test check_outcome routing
        cq4 = DummyCallbackQuery("check_outcome_SIG3", user_id=45)
        upd4 = DummyUpdate(cq4)
        await mod._global_callback_handler(upd4, ctx)
        assert any(c[0] == "check_outcome" for c in calls)

        # Test mt5_status routing
        cq4b = DummyCallbackQuery("mt5_status", user_id=45)
        upd4b = DummyUpdate(cq4b)
        await mod._global_callback_handler(upd4b, ctx)
        assert any(c[0] == "mt5_status" for c in calls)

        # Test unknown callback falls back to default handler
        cq5 = DummyCallbackQuery("unknown_foobar", user_id=46)
        upd5 = DummyUpdate(cq5)
        await mod._global_callback_handler(upd5, ctx)
        assert any(c[0] == "default" for c in calls)

        # Ensure all CallbackQuery.answer() were called to stop the spinner
        assert cq.answered and cq2.answered and cq3.answered and cq4.answered and cq4b.answered and cq5.answered

    asyncio.run(_runner())


def test_button_click_handler_routes_nav_execution(monkeypatch):
    async def _runner():
        mod = importlib.import_module("signalrank_telegram.commands")

        calls = []

        async def execution_stub(update, context):
            calls.append(("execution", update, context))

        monkeypatch.setattr(mod, "execution_command", execution_stub)

        ctx = DummyContext()
        cq = DummyCallbackQuery("nav_execution", user_id=42)
        upd = DummyUpdate(cq)
        await mod.button_click_handler(upd, ctx)

        assert any(c[0] == "execution" for c in calls)
        assert cq.answered

    asyncio.run(_runner())
