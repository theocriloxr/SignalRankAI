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


class DummyContext:
    def __init__(self):
        self.bot = types.SimpleNamespace()


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

        # Test unknown callback falls back to default handler
        cq5 = DummyCallbackQuery("unknown_foobar", user_id=46)
        upd5 = DummyUpdate(cq5)
        await mod._global_callback_handler(upd5, ctx)
        assert any(c[0] == "default" for c in calls)

        # Ensure all CallbackQuery.answer() were called to stop the spinner
        assert cq.answered and cq2.answered and cq3.answered and cq4.answered and cq5.answered

    asyncio.run(_runner())
