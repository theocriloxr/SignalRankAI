"""Legacy Telegram bot entrypoint (disabled by default).

This repo's primary Telegram bot implementation is in `signalrank_telegram/`.
Historically, a separate bot lived under `telegram/` and depended on the old
SQLite-backed layer.

We keep this module name for backward compatibility with docs/automation, but
we *hard block* it unless explicitly opted in.
"""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    if not _env_bool("ALLOW_LEGACY_TELEGRAM_BOT", False):
        raise RuntimeError(
            "Legacy telegram.bot is disabled. "
            "Use RUN_MODE=bot python main.py (recommended), "
            "or set ALLOW_LEGACY_TELEGRAM_BOT=true to explicitly opt in."
        )

    # Delegate to the maintained bot.
    from signalrank_telegram.bot import run_bot

    run_bot()


if __name__ == "__main__":
    main()

