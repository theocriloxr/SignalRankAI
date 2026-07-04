from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_every_signal_success_path_requires_telegram_proof() -> None:
    bot_source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    pg_source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    assert "sent_ok=True" not in bot_source
    assert "missing_telegram_ack" in pg_source
    assert "telegram_message_id" in pg_source
    assert "SignalDelivery.telegram_message_id.is_not(None)" in pg_source


def test_owner_delivery_debug_and_signal_supersession_are_registered() -> None:
    commands_source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    bot_source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    pg_source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    assert "async def delivery_debug_command" in commands_source
    assert 'CommandHandler("delivery_debug"' in bot_source
    assert 'status="superseded"' in pg_source


def test_excursion_tracker_preserves_best_and_worst_prices() -> None:
    from engine.realtime_outcome_tracker import _EXCURSION_CACHE, _record_excursion

    signal_id = "excursion-test"
    _EXCURSION_CACHE.pop(signal_id, None)
    _record_excursion(signal_id, "long", 100.0, 104.0)
    result = _record_excursion(signal_id, "long", 100.0, 97.0)
    assert result["mfe_pct"] == 4.0
    assert result["mae_pct"] == -3.0
    _EXCURSION_CACHE.pop(signal_id, None)


def test_outcomes_preserve_partial_win_and_excursion_metadata() -> None:
    source = (ROOT / "engine" / "realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert 'canonical_outcome = "partial_win"' in source
    assert '"reversed_after_tp": bool(status_l == "sl" and tp_hit_index > 0)' in source
    assert '"mfe_pct"' in source and '"mae_pct"' in source


def test_vip_formatter_always_has_a_reason() -> None:
    from signalrank_telegram.tier_signal_formatter import format_vip_signal

    message = format_vip_signal(
        {
            "signal_id": "fallback-reason",
            "asset": "EURUSD",
            "direction": "long",
            "timeframe": "1h",
            "entry": 1.1,
            "stop_loss": 1.09,
            "take_profit": [1.12],
            "score": 90,
            "strategy": "EMA trend",
            "regime": "trending",
        }
    )
    assert "Why:" in message
    why_line = next(line for line in message.splitlines() if line.startswith("Why:"))
    assert why_line.removeprefix("Why:").strip()


def test_calendar_has_free_timed_feed_before_keyed_fallback() -> None:
    source = (ROOT / "services" / "economic_calendar.py").read_text(encoding="utf-8")
    fetch_flow = source.split("async def fetch_economic_events", 1)[1].split(
        "async def is_no_trade_zone", 1
    )[0]
    assert fetch_flow.index("_fetch_forex_factory") < fetch_flow.index("_fetch_finnhub")
    assert "FOREX_FACTORY_CALENDAR_URL" in source


def test_gemini_review_uses_typed_runtime_state_storage() -> None:
    source = (ROOT / "services" / "gemini_ml.py").read_text(encoding="utf-8")
    assert "async def get_last_gemini_review" in source
    assert ":value::jsonb" not in source
    assert "await _persist_gemini_review(result, db_session)" in source
