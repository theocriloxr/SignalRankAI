"""Messages we send satisfy the Telegram Bot API contract (1 Nov 2026).

Telegram rejects a whole message ("can't parse entities") when HTML mode text
uses an unsupported tag, an unclosed or misnested tag, or a raw ``<`` / ``&``;
text is capped at 4096 characters and each button's callback_data at 64
bytes. Checked offline against the documented rules, with hostile text in the
fields that come from outside our code (strategy names, AI review text).
"""
from __future__ import annotations

import html
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest

# https://core.telegram.org/bots/api#html-style
ALLOWED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "span", "tg-spoiler", "a", "tg-emoji",
           "code", "pre", "blockquote"}
TOKEN = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^<>]*)?)>|&(#\d+|#x[0-9a-fA-F]+|lt|gt|amp|quot);|[<&]")
HOSTILE = 'Breakout <v2> & "retest" <script>'


def telegram_html_errors(text: str) -> list[str]:
    errors, stack = [], []
    for m in TOKEN.finditer(text):
        raw = m.group(0)
        if raw in {"<", "&"}:
            errors.append(f"unescaped {raw!r} at {m.start()}: {text[max(0, m.start() - 20):m.start() + 20]!r}")
            continue
        if m.group(4):
            continue
        closing, tag, attrs = m.group(1), m.group(2).lower(), (m.group(3) or "").strip()
        if tag not in ALLOWED:
            errors.append(f"unsupported tag <{tag}>")
            continue
        if tag == "span" and not closing and attrs != 'class="tg-spoiler"':
            errors.append("span without class=tg-spoiler")
        if closing:
            if not stack or stack[-1] != tag:
                errors.append(f"misnested </{tag}> (open: {stack})")
            else:
                stack.pop()
        else:
            stack.append(tag)
    if stack:
        errors.append(f"unclosed {stack}")
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    if len(plain) > 4096:
        errors.append(f"text {len(plain)} > 4096 characters")
    return errors


def callback_errors(markup) -> list[str]:
    errors = []
    for row in getattr(markup, "inline_keyboard", None) or ():
        for button in row:
            data = getattr(button, "callback_data", None)
            if data is not None and len(str(data).encode()) > 64:
                errors.append(f"callback_data {len(str(data).encode())} bytes: {data!r}")
    return errors


def test_the_validator_follows_the_documented_rules():
    assert not telegram_html_errors("<b>BTC</b> &amp; <code>1 &lt; 2</code> <a href=\"https://x.test\">x</a>")
    assert telegram_html_errors("RSI < 30")
    assert telegram_html_errors("A & B")
    assert telegram_html_errors("<b>open")
    assert telegram_html_errors("<b><i>x</b></i>")
    assert telegram_html_errors("<div>x</div>")
    assert telegram_html_errors("x" * 4097)


def _signal(**extra) -> dict:
    sid = str(uuid4())
    return {"signal_id": sid, "id": sid, "asset": "BTCUSDT", "timeframe": "15m", "direction": "long", "entry": 100.0,
            "stop_loss": 98.0, "take_profit": [102.0, 104.0, 106.0], "take_profits": [102.0, 104.0, 106.0],
            "score": 92.0, "rr_ratio": 3.0, "regime": "trending", "session": "london", "strategy_name": HOSTILE,
            "strategy": HOSTILE, "ai_review_reason": "RSI < 30 & falling <fast>", "trade_logic": HOSTILE,
            "invalidation": "close < 98 & volume > 2x", "confluence": "4/5 <strong>", "created_at": "2026-11-01T10:00:00+00:00",
            **extra}


@pytest.mark.parametrize("tier", ["free", "premium", "vip", "admin", "owner"])
def test_signal_messages_for_every_tier_are_valid_with_hostile_fields(tier):
    from signalrank_telegram.formatter import format_signal

    text = format_signal(_signal(), display_tier=tier, user_tier=tier)
    assert text, tier
    assert telegram_html_errors(text) == [], (tier, telegram_html_errors(text), text[:600])


def test_signal_and_monitor_keyboards_fit_the_callback_limit():
    import signalrank_telegram.bot as bot
    from engine.realtime_outcome_tracker import _outcome_monitoring_keyboard

    sid = str(uuid4())
    markups = [bot._build_signal_keyboard(sid, signal=_signal(signal_id=sid), counts={"taking_it": 3, "watching": 9}),
               bot._build_monitor_keyboard(sid)]
    markups += [_outcome_monitoring_keyboard(sid, status) for status in ("tp1", "tp2", "tp3", "sl", "missed_entry")]
    for markup in markups:
        assert callback_errors(markup) == []


# --- What the delivery path actually sends, on real PostgreSQL ---------------------------------------

from tests.test_master_p0_postgres_integration import postgres_database  # noqa: E402,F401
from tests.test_signal_pipeline_postgres_20261030 import _signal as _pipeline_signal  # noqa: E402
from tests.test_signal_pipeline_postgres_20261030 import _stored, _vip_user, network_edges  # noqa: E402,F401


@pytest.mark.asyncio
async def test_every_message_sent_for_a_hostile_signal_is_valid(postgres_database, network_edges):  # noqa: F811
    import signalrank_telegram.bot as bot
    from engine.realtime_outcome_tracker import reconcile_signal_now
    from signalrank_telegram.commands import proof_command

    telegram_id = await _vip_user()
    asset = f"H{uuid4().hex[:6].upper()}USDT"
    network_edges.prices[asset] = 100.0
    payload = {**_pipeline_signal(asset), "strategy_name": HOSTILE, "strategy_group": "hostile",
               "ai_review_reason": "RSI < 30 & falling <fast>", "trade_logic": HOSTILE,
               "invalidation": "close < 98 & volume > 2x"}
    stored = await _stored(payload)
    assert await bot.dispatch_signals_async([dict(stored)], telegram_id) == 1
    for price in (100.0, 102.05, 97.9):  # entry, TP1, then stopped
        network_edges.prices[asset] = price
        await reconcile_signal_now(stored["signal_id"])
    replies: list[str] = []

    async def reply_text(text, **kwargs):
        replies.append(text)

    chat = SimpleNamespace(type="private", id=telegram_id)
    await proof_command(SimpleNamespace(message=SimpleNamespace(reply_text=reply_text, chat=chat), effective_chat=chat,
                                        effective_user=SimpleNamespace(id=telegram_id)), SimpleNamespace(args=[]))
    sent = [m for m in network_edges.telegram.sent if m["chat_id"] == telegram_id]
    assert len(sent) >= 3, [m["text"][:80] for m in sent]  # signal, readiness note, outcome(s)
    for message in sent:
        if message.get("parse_mode") == "HTML":
            assert telegram_html_errors(message["text"]) == [], message["text"][:600]
        assert callback_errors(message.get("reply_markup")) == []
    assert all(telegram_html_errors(r) == [] for r in replies), replies
