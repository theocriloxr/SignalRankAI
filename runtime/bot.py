"""Telegram interaction role adapter."""

from __future__ import annotations


def run() -> None:
    from signalrank_telegram.bot import run_bot

    run_bot()


start = run

__all__ = ["run", "start"]
