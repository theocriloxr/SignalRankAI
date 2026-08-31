from __future__ import annotations

import re
from pathlib import Path

from signalrank_telegram.command_resilience import safe_command_error


ROOT = Path(__file__).resolve().parents[1]


def test_safe_command_error_returns_reference_without_raw_exception() -> None:
    secret = "postgresql://user:password@example.invalid/db"
    message = safe_command_error("Could not load data.", RuntimeError(secret))
    assert secret not in message
    assert re.search(r"Reference: CMD-[A-F0-9]{8}", message)


def test_sensitive_command_arguments_are_redacted_from_audit() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    for command in (
        "unlock",
        "mt5_link",
        "mt5link",
        "mt5",
        "connect_broker",
        "setwebhook",
        "apikey",
        "login_code",
        "link",
    ):
        assert f'"{command}"' in source
    assert 'meta["args_redacted"] = True' in source


def test_public_replies_do_not_interpolate_raw_exceptions() -> None:
    reply_pattern = re.compile(
        r"(?:reply_text|edit_text)\(f?[\"'][^\n]*(?:\{e\}|\{exc\}|\{err\}|\{error\})"
    )
    violations = []
    for path in (ROOT / "signalrank_telegram").glob("*.py"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if reply_pattern.search(line):
                violations.append(f"{path.name}:{line_number}")
    assert not violations, f"raw exception text exposed in command replies: {violations}"
