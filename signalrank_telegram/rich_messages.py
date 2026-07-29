"""Telegram Bot API 10.1 rich-message helpers.

The Bot API now supports sendRichMessage with rich HTML/Markdown blocks. This
module is deliberately optional and fail-safe: the existing HTML text message is
always the compatibility fallback until the deployed python-telegram-bot version
and all target clients are proven stable with rich messages.
"""
from __future__ import annotations

import html
import logging
import os
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)


def rich_messages_enabled() -> bool:
    """Return whether experimental rich messages are explicitly certified.

    ``sendRichMessage`` is not treated as a normal feature toggle because some
    Telegram clients/export paths flatten structural tags into labels such as
    ``Table`` and hide the actual signal values. Operators must therefore set
    both flags after verifying the exact deployed bot/client combination.
    """
    enabled = str(os.getenv("TELEGRAM_RICH_MESSAGES_ENABLED", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
    certified = str(os.getenv("TELEGRAM_RICH_MESSAGES_CERTIFIED", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
    mode = str(os.getenv("TELEGRAM_RICH_MESSAGES_MODE", "off") or "off").strip().lower()
    allowed = bool(enabled and certified and mode == "canary")
    if enabled and not allowed:
        logger.warning(
            "[rich_messages] structural rich cards blocked mode=%s certified=%s; using canonical HTML signal cards",
            mode, certified,
        )
    return allowed


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        f = float(value)
        if abs(f) >= 1000:
            return f"{f:,.2f}"
        return f"{f:.{digits}f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value or "—")


def _targets(signal: dict[str, Any]) -> list[float]:
    import json
    raw = signal.get("take_profit") or signal.get("take_profits") or signal.get("targets") or signal.get("tp")
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    else:
        parsed = raw
    if isinstance(parsed, dict):
        parsed = list(parsed.values())
    if not isinstance(parsed, (list, tuple)):
        parsed = [parsed]
    out: list[float] = []
    for item in parsed:
        if isinstance(item, dict):
            item = item.get("price") or item.get("target") or item.get("value")
        try:
            out.append(float(item))
        except Exception:
            continue
    return out[:3]


def build_signal_rich_html(signal: dict[str, Any], fallback_text: str = "") -> str:
    """Build rich HTML for Telegram sendRichMessage.

    Uses structural tags supported by rich messages: headings, tables, and
    details. If Telegram rejects rich HTML, the caller must fall back to the
    existing plain HTML signal card.
    """
    asset = html.escape(str(signal.get("asset") or signal.get("symbol") or "Signal"))
    direction = html.escape(str(signal.get("direction") or "").upper())
    tf = html.escape(str(signal.get("timeframe") or "—"))
    score = html.escape(str(signal.get("score") or signal.get("confidence") or "—"))
    live = signal.get("current_price") or signal.get("live_price")
    drift = signal.get("entry_drift_pct") or signal.get("price_distance_pct")
    ai = signal.get("ai_review") or signal.get("ai_review_summary") or signal.get("gemini_review") or ""
    why = signal.get("why") or signal.get("reason") or signal.get("strategy_reason") or ""
    sid = html.escape(str(signal.get("signal_id") or signal.get("id") or "")[:13])
    rows = [
        ("Entry", _fmt(signal.get("entry"))),
        ("Stop", _fmt(signal.get("stop_loss") or signal.get("sl"))),
    ]
    for idx, tp in enumerate(_targets(signal), 1):
        rows.append((f"TP{idx}", _fmt(tp)))
    if live:
        rows.append(("Live", _fmt(live)))
    if drift:
        rows.append(("Drift", f"{_fmt(drift, 2)}%"))
    table_rows = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{html.escape(value)}</td></tr>" for label, value in rows
    )
    details_source = "\n".join(part for part in [str(why or ""), str(ai or "")] if part).strip()
    if not details_source and fallback_text:
        # Preserve useful canonical-card context rather than displaying an empty placeholder.
        import re
        details_source = re.sub(r"<[^>]+>", " ", str(fallback_text))
        details_source = " ".join(details_source.split())[:1200]
    details_text = html.escape(details_source or "The canonical signal card contains the verified trade levels and context.")
    return (
        f"<h3>🚨 VIP SIGNAL — {asset} {direction}</h3>"
        f"<p><b>Timeframe:</b> {tf} • <b>Score:</b> {score} • <b>ID:</b> {sid}</p>"
        f"<table>{table_rows}</table>"
        f"<details><summary>AI / technical explanation</summary><p>{details_text}</p></details>"
    )


def _reply_markup_to_dict(reply_markup: Any) -> Any:
    if reply_markup is None:
        return None
    if hasattr(reply_markup, "to_dict"):
        return reply_markup.to_dict()
    return reply_markup


async def send_rich_message_raw(bot: Any, *, chat_id: int, rich_html: str, timeout: float = 10.0, **kwargs: Any) -> Any:
    """Send rich message via raw Bot API for library versions without wrapper support."""
    import asyncio
    import requests

    token = getattr(bot, "token", None)
    if not token:
        raise RuntimeError("bot token unavailable for raw sendRichMessage")
    payload: dict[str, Any] = {
        "chat_id": int(chat_id),
        "rich_message": {"html": str(rich_html), "skip_entity_detection": True},
    }
    for key in ("disable_notification", "protect_content", "allow_paid_broadcast"):
        if key in kwargs and kwargs[key] is not None:
            payload[key] = kwargs[key]
    reply_markup = _reply_markup_to_dict(kwargs.get("reply_markup"))
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    def _post() -> dict[str, Any]:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendRichMessage",
            json=payload,
            timeout=timeout,
        )
        try:
            data = resp.json()
        except Exception:
            data = {"ok": False, "description": resp.text[:500]}
        if not resp.ok or not data.get("ok"):
            raise RuntimeError(f"sendRichMessage failed status={resp.status_code} data={data}")
        return data

    data = await asyncio.to_thread(_post)
    result = data.get("result") or {}
    chat = result.get("chat") or {"id": int(chat_id)}
    return SimpleNamespace(
        message_id=int(result.get("message_id") or 0),
        chat=SimpleNamespace(id=int(chat.get("id", chat_id))),
        raw=result,
    )


__all__ = ["rich_messages_enabled", "build_signal_rich_html", "send_rich_message_raw"]
