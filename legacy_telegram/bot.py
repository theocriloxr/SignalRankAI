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
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def main() -> None:
    if not _env_bool("ALLOW_LEGACY_TELEGRAM_BOT", False):
        raise RuntimeError(
            "Legacy legacy_telegram.bot is disabled. "
            "Use RUN_MODE=bot python main.py (recommended), "
            "or set ALLOW_LEGACY_TELEGRAM_BOT=true to explicitly opt in."
        )

    # Delegate to the maintained bot.
    from signalrank_telegram.bot import run_bot

    run_bot()


if __name__ == "__main__":
    main()

