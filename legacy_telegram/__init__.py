"""Disabled legacy Telegram implementation.

The maintained production bot lives in :mod:`signalrank_telegram`. Keeping the
legacy code under a distinct package name prevents it from shadowing the
``python-telegram-bot`` dependency's top-level :mod:`telegram` package.
"""
