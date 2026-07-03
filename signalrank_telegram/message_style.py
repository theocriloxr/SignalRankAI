"""Telegram message cleanup helpers.

This module intentionally stays lightweight: it fixes common mojibake emitted by
older formatters without forcing every command to be rewritten at once.
"""

from __future__ import annotations


_MOJIBAKE_REPLACEMENTS = {
    "âœ…": "✅",
    "âŒ": "❌",
    "âš ï¸": "⚠️",
    "âš¡": "⚡",
    "â³": "⏳",
    "â°": "⏰",
    "â±ï¸": "⏱️",
    "â›”": "⛔",
    "â€”": "-",
    "â€“": "-",
    "â€¢": "•",
    "â­": "⭐",
    "â­•": "⭕",
    "ðŸš€": "🚀",
    "ðŸ”¥": "🔥",
    "ðŸ”’": "🔒",
    "ðŸ“Œ": "📌",
    "ðŸ“‹": "📋",
    "ðŸ“Š": "📊",
    "ðŸ“ˆ": "📈",
    "ðŸ“‰": "📉",
    "ðŸ“†": "📆",
    "ðŸ’¡": "💡",
    "ðŸ§ ": "🧠",
    "ðŸŸ¢": "🟢",
    "ðŸŸ¡": "🟡",
    "ðŸ”´": "🔴",
    "â•": "=",
}


def clean_message_text(text: str | None) -> str:
    """Normalize Telegram text before it is sent or returned by formatters."""
    if text is None:
        return ""
    cleaned = str(text)
    for bad, good in _MOJIBAKE_REPLACEMENTS.items():
        cleaned = cleaned.replace(bad, good)
    lines = [line.rstrip() for line in cleaned.replace("\r\n", "\n").replace("\r", "\n").split("\n")]

    compact: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        compact.append(line)
        previous_blank = blank
    return "\n".join(compact).strip()
