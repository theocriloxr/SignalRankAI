"""Every registered Telegram command runs without a code-level crash (owner request, 9-10 Nov 2026).

"Update all commands and ensure they are all working." Each handler is called
as a Free user and as the owner with stand-in Telegram objects and no database.
Missing infrastructure (no DB, timeouts) is expected here; a NameError,
ImportError, AttributeError, TypeError or KeyError is a bug in the command.
Found and fixed with this test: /public_test_status (KeyError on a renamed
flag) and /owner_test_delivery plus the asset commands (AssetSpec.symbol).
"""
from __future__ import annotations

import asyncio
import importlib
import pkgutil
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
CODE_BUGS = (NameError, ImportError, AttributeError, TypeError, KeyError, UnboundLocalError)


def _fakes(uid: int):
    msg = MagicMock()
    for name in ("reply_text", "reply_html", "reply_photo", "reply_document", "edit_text"):
        setattr(msg, name, AsyncMock())
    msg.text = "/x"
    msg.chat = SimpleNamespace(id=uid, type="private")
    user = SimpleNamespace(id=uid, username="tester", first_name="T", last_name=None, language_code="en", is_bot=False)
    update = MagicMock()
    update.message = update.effective_message = msg
    update.effective_user = user
    update.effective_chat = SimpleNamespace(id=uid, type="private")
    update.callback_query = None
    context = MagicMock()
    context.args = []
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.user_data, context.bot_data = {}, {}
    return update, context


def _handlers():
    import signalrank_telegram as package
    import signalrank_telegram.bot as bot

    source = (ROOT / "signalrank_telegram" / "bot.py").read_text("utf-8")
    pairs = re.findall(r'CommandHandler\(\s*"([a-z0-9_]+)",\s*(?:_audit_handler\("[a-z0-9_]+",\s*)?([A-Za-z0-9_]+)',
                       source)
    modules = [bot]
    for info in pkgutil.iter_modules(package.__path__):
        try:
            modules.append(importlib.import_module(f"signalrank_telegram.{info.name}"))
        except Exception:
            continue
    for name, function_name in pairs:
        function = next((getattr(m, function_name) for m in modules if hasattr(m, function_name)), None)
        yield name, function_name, function


def test_every_command_handler_runs_without_a_code_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OWNER_IDS", "222")

    async def run():
        problems = []
        for name, function_name, function in _handlers():
            if function is None:
                if function_name.startswith("_"):
                    continue  # inline fallback defined inside the bot setup
                problems.append(f"/{name}: handler {function_name} not found")
                continue
            for uid in (111, 222):
                update, context = _fakes(uid)
                try:
                    await asyncio.wait_for(function(update, context), timeout=3)
                except asyncio.TimeoutError:
                    pass
                except CODE_BUGS as exc:
                    problems.append(f"/{name} (user {uid}): {type(exc).__name__}: {exc}")
                except Exception:
                    pass  # no database, no network: expected in this test
        return problems

    problems = asyncio.run(run())
    assert not problems, "\n".join(problems)
