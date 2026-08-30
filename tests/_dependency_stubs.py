"""Test-only fallbacks for optional runtime dependencies.

The production image must install requirements.txt. These stubs are installed only by
pytest's root conftest when a dependency is unavailable, allowing the repository's
pure/unit tests to collect in constrained offline environments without shadowing the
real packages at runtime.
"""
from __future__ import annotations

import asyncio
import re
import sys
import types
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable


def _install_telegram() -> None:
    try:
        __import__("telegram")
        return
    except ModuleNotFoundError:
        pass

    telegram = types.ModuleType("telegram")
    ext = types.ModuleType("telegram.ext")
    helpers = types.ModuleType("telegram.helpers")
    constants = types.ModuleType("telegram.constants")
    errors = types.ModuleType("telegram.error")

    class TelegramError(Exception):
        pass

    class RetryAfter(TelegramError):
        def __init__(self, retry_after: float = 0, message: str | None = None):
            self.retry_after = retry_after
            super().__init__(message or f"Retry after {retry_after}")

    class BadRequest(TelegramError):
        pass

    class Forbidden(TelegramError):
        pass

    @dataclass
    class InlineKeyboardButton:
        text: str
        callback_data: str | None = None
        url: str | None = None
        web_app: Any = None

    class InlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard

    @dataclass
    class KeyboardButton:
        text: str
        request_contact: bool | None = None
        request_location: bool | None = None
        web_app: Any = None

    class ReplyKeyboardMarkup:
        def __init__(self, keyboard, **kwargs):
            self.keyboard = keyboard
            for key, value in kwargs.items():
                setattr(self, key, value)

    class ReplyKeyboardRemove:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    @dataclass
    class WebAppInfo:
        url: str

    @dataclass
    class MenuButtonWebApp:
        text: str
        web_app: WebAppInfo

    @dataclass
    class BotCommand:
        command: str
        description: str

        def __iter__(self):
            yield self.command
            yield self.description

    class BotCommandScopeDefault:
        pass

    class BotCommandScopeAllPrivateChats:
        pass

    @dataclass
    class BotCommandScopeChat:
        chat_id: int | str

    class Update:
        def __init__(self, update_id: int | None = None, **kwargs):
            self.update_id = update_id
            for key, value in kwargs.items():
                setattr(self, key, value)

        @classmethod
        def de_json(cls, payload: dict[str, Any], bot: Any = None):
            return cls(**payload)

    class Bot:
        def __init__(self, token: str | None = None, **kwargs):
            self.token = token
            self.id = kwargs.get("id", 0)

        async def get_me(self):
            return SimpleNamespace(id=self.id, username="test_bot")

        async def send_message(self, *args, **kwargs):
            return SimpleNamespace(message_id=1, chat_id=kwargs.get("chat_id"))

        async def send_photo(self, *args, **kwargs):
            return SimpleNamespace(message_id=1, chat_id=kwargs.get("chat_id"))

        async def set_webhook(self, *args, **kwargs):
            return True

        async def delete_webhook(self, *args, **kwargs):
            return True

        async def get_webhook_info(self):
            return SimpleNamespace(url="", pending_update_count=0, last_error_date=None, last_error_message=None)

        async def set_my_commands(self, *args, **kwargs):
            return True

        async def delete_my_commands(self, *args, **kwargs):
            return True

        async def set_chat_menu_button(self, *args, **kwargs):
            return True

        def __getattr__(self, name: str):
            async def _async_noop(*args, **kwargs):
                return True

            return _async_noop

    class _Filter:
        def __init__(self, predicate: Callable[[Any], bool] | None = None, name: str = ""):
            self.predicate = predicate or (lambda _value: True)
            self.name = name

        def __and__(self, other):
            return _Filter(lambda value: self(value) and other(value), f"({self.name}&{other.name})")

        def __or__(self, other):
            return _Filter(lambda value: self(value) or other(value), f"({self.name}|{other.name})")

        def __invert__(self):
            return _Filter(lambda value: not self(value), f"~{self.name}")

        def __call__(self, value):
            try:
                return bool(self.predicate(value))
            except Exception:
                return False

    class _Filters(SimpleNamespace):
        def Regex(self, pattern):
            regex = re.compile(pattern)
            return _Filter(lambda value: bool(regex.search(str(getattr(value, "text", value) or ""))), f"Regex({pattern})")

    filters = _Filters(
        TEXT=_Filter(name="TEXT"),
        COMMAND=_Filter(name="COMMAND"),
        ALL=_Filter(name="ALL"),
        PHOTO=_Filter(name="PHOTO"),
        Document=SimpleNamespace(ALL=_Filter(name="Document.ALL")),
    )

    class BaseHandler:
        def __init__(self, callback=None, *args, **kwargs):
            self.callback = callback
            self.block = kwargs.get("block", True)
            self.pattern = kwargs.get("pattern")

    class CommandHandler(BaseHandler):
        def __init__(self, command, callback, *args, **kwargs):
            super().__init__(callback, *args, **kwargs)
            self.command = command
            self.commands = frozenset([command] if isinstance(command, str) else command)

    class MessageHandler(BaseHandler):
        def __init__(self, filters_arg, callback, *args, **kwargs):
            super().__init__(callback, *args, **kwargs)
            self.filters = filters_arg

    class CallbackQueryHandler(BaseHandler):
        def __init__(self, callback, pattern=None, *args, **kwargs):
            super().__init__(callback, *args, pattern=pattern, **kwargs)

    class ConversationHandler(BaseHandler):
        END = -1
        TIMEOUT = -2

        def __init__(self, entry_points=None, states=None, fallbacks=None, **kwargs):
            super().__init__(None)
            self.entry_points = entry_points or []
            self.states = states or {}
            self.fallbacks = fallbacks or []
            self.conversation_timeout = kwargs.get("conversation_timeout")

    class Defaults:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class ContextTypes:
        DEFAULT_TYPE = SimpleNamespace

    class _Updater:
        running = False

        async def start_polling(self, *args, **kwargs):
            self.running = True

        async def stop(self):
            self.running = False

    class Application:
        def __init__(self, token: str | None = None, defaults=None, post_init=None, **kwargs):
            self.bot = Bot(token=token)
            self.handlers: dict[int, list[Any]] = {}
            self.error_handlers: list[Any] = []
            self.defaults = defaults
            self.post_init = post_init
            self.updater = _Updater()
            self.running = False

        @classmethod
        def builder(cls):
            return _ApplicationBuilder(cls)

        def add_handler(self, handler, group: int = 0):
            self.handlers.setdefault(group, []).append(handler)

        def add_error_handler(self, callback, *args, **kwargs):
            self.error_handlers.append(callback)

        async def initialize(self):
            return None

        async def start(self):
            self.running = True
            if self.post_init:
                result = self.post_init(self)
                if asyncio.iscoroutine(result):
                    await result

        async def stop(self):
            self.running = False

        async def shutdown(self):
            return None

        async def process_update(self, update):
            return None

    class _ApplicationBuilder:
        def __init__(self, application_cls):
            self.application_cls = application_cls
            self.kwargs: dict[str, Any] = {}

        def token(self, token):
            self.kwargs["token"] = token
            return self

        def defaults(self, defaults):
            self.kwargs["defaults"] = defaults
            return self

        def post_init(self, callback):
            self.kwargs["post_init"] = callback
            return self

        def concurrent_updates(self, value):
            self.kwargs["concurrent_updates"] = value
            return self

        def connect_timeout(self, value):
            self.kwargs["connect_timeout"] = value
            return self

        def read_timeout(self, value):
            self.kwargs["read_timeout"] = value
            return self

        def write_timeout(self, value):
            self.kwargs["write_timeout"] = value
            return self

        def pool_timeout(self, value):
            self.kwargs["pool_timeout"] = value
            return self

        def get_updates_connect_timeout(self, value):
            return self

        def get_updates_read_timeout(self, value):
            return self

        def get_updates_write_timeout(self, value):
            return self

        def get_updates_pool_timeout(self, value):
            return self

        def build(self):
            return self.application_cls(**self.kwargs)

        def __getattr__(self, _name):
            def _chain(*args, **kwargs):
                return self

            return _chain

    class ParseMode:
        HTML = "HTML"
        MARKDOWN = "Markdown"
        MARKDOWN_V2 = "MarkdownV2"

    def escape_markdown(text: str, version: int = 1, entity_type: str | None = None) -> str:
        text = str(text)
        chars = r"_*[]()~`>#+-=|{}.!" if version == 2 else r"_*[`"
        return re.sub(r"([" + re.escape(chars) + r"])", r"\\\1", text)

    telegram.Update = Update
    telegram.Bot = Bot
    telegram.InlineKeyboardButton = InlineKeyboardButton
    telegram.InlineKeyboardMarkup = InlineKeyboardMarkup
    telegram.KeyboardButton = KeyboardButton
    telegram.ReplyKeyboardMarkup = ReplyKeyboardMarkup
    telegram.ReplyKeyboardRemove = ReplyKeyboardRemove
    telegram.WebAppInfo = WebAppInfo
    telegram.MenuButtonWebApp = MenuButtonWebApp
    telegram.BotCommand = BotCommand
    telegram.BotCommandScopeDefault = BotCommandScopeDefault
    telegram.BotCommandScopeAllPrivateChats = BotCommandScopeAllPrivateChats
    telegram.BotCommandScopeChat = BotCommandScopeChat

    ext.Application = Application
    ext.CommandHandler = CommandHandler
    ext.MessageHandler = MessageHandler
    ext.CallbackQueryHandler = CallbackQueryHandler
    ext.ConversationHandler = ConversationHandler
    ext.ContextTypes = ContextTypes
    ext.Defaults = Defaults
    ext.filters = filters

    helpers.escape_markdown = escape_markdown
    constants.ParseMode = ParseMode
    errors.TelegramError = TelegramError
    errors.RetryAfter = RetryAfter
    errors.BadRequest = BadRequest
    errors.Forbidden = Forbidden

    sys.modules.update(
        {
            "telegram": telegram,
            "telegram.ext": ext,
            "telegram.helpers": helpers,
            "telegram.constants": constants,
            "telegram.error": errors,
        }
    )


def _install_apscheduler() -> None:
    try:
        __import__("apscheduler")
        return
    except ModuleNotFoundError:
        pass

    apscheduler = types.ModuleType("apscheduler")
    schedulers = types.ModuleType("apscheduler.schedulers")
    sched_background = types.ModuleType("apscheduler.schedulers.background")
    sched_asyncio = types.ModuleType("apscheduler.schedulers.asyncio")
    triggers = types.ModuleType("apscheduler.triggers")
    trigger_interval = types.ModuleType("apscheduler.triggers.interval")
    jobstores = types.ModuleType("apscheduler.jobstores")
    jobstores_sqlalchemy = types.ModuleType("apscheduler.jobstores.sqlalchemy")
    executors = types.ModuleType("apscheduler.executors")
    executors_pool = types.ModuleType("apscheduler.executors.pool")

    @dataclass
    class _Job:
        func: Any
        trigger: Any = None
        id: str | None = None
        name: str | None = None
        kwargs: dict[str, Any] | None = None

        def remove(self):
            return None

    class _Scheduler:
        STATE_STOPPED = 0
        STATE_RUNNING = 1

        def __init__(self, *args, **kwargs):
            self._jobs: list[_Job] = []
            self.running = False
            self.state = self.STATE_STOPPED
            self.jobstores = kwargs.get("jobstores", {})
            self.executors = kwargs.get("executors", {})
            self.job_defaults = kwargs.get("job_defaults", {})
            self.timezone = kwargs.get("timezone")

        def add_job(self, func, trigger=None, *args, **kwargs):
            job_id = kwargs.get("id") or kwargs.get("name") or f"job-{len(self._jobs) + 1}"
            replace_existing = kwargs.get("replace_existing", False)
            if replace_existing:
                self._jobs = [job for job in self._jobs if job.id != job_id]
            job = _Job(func=func, trigger=trigger, id=job_id, name=kwargs.get("name"), kwargs=kwargs)
            self._jobs.append(job)
            return job

        def get_jobs(self, jobstore=None):
            return list(self._jobs)

        def get_job(self, job_id, jobstore=None):
            return next((job for job in self._jobs if job.id == job_id), None)

        def remove_job(self, job_id, jobstore=None):
            self._jobs = [job for job in self._jobs if job.id != job_id]

        def remove_all_jobs(self, jobstore=None):
            self._jobs.clear()

        def start(self, paused: bool = False):
            self.running = True
            self.state = self.STATE_RUNNING

        def shutdown(self, wait: bool = True):
            self.running = False
            self.state = self.STATE_STOPPED

        def pause(self):
            self.running = False

        def resume(self):
            self.running = True

        def __enter__(self):
            self.start()
            return self

        def __exit__(self, exc_type, exc, tb):
            self.shutdown(wait=False)

    class BackgroundScheduler(_Scheduler):
        pass

    class AsyncIOScheduler(_Scheduler):
        pass

    class IntervalTrigger:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class SQLAlchemyJobStore:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class ThreadPoolExecutor:
        def __init__(self, max_workers=10, *args, **kwargs):
            self.max_workers = max_workers

    sched_background.BackgroundScheduler = BackgroundScheduler
    sched_asyncio.AsyncIOScheduler = AsyncIOScheduler
    trigger_interval.IntervalTrigger = IntervalTrigger
    jobstores_sqlalchemy.SQLAlchemyJobStore = SQLAlchemyJobStore
    executors_pool.ThreadPoolExecutor = ThreadPoolExecutor

    sys.modules.update(
        {
            "apscheduler": apscheduler,
            "apscheduler.schedulers": schedulers,
            "apscheduler.schedulers.background": sched_background,
            "apscheduler.schedulers.asyncio": sched_asyncio,
            "apscheduler.triggers": triggers,
            "apscheduler.triggers.interval": trigger_interval,
            "apscheduler.jobstores": jobstores,
            "apscheduler.jobstores.sqlalchemy": jobstores_sqlalchemy,
            "apscheduler.executors": executors,
            "apscheduler.executors.pool": executors_pool,
        }
    )


def install_optional_dependency_stubs() -> None:
    _install_telegram()
    _install_apscheduler()
