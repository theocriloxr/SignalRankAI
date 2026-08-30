from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_migration_0025_indexes_started_at_not_missing_created_at():
    text = source("db/migrations/versions/0025_adaptive_strategy.py")
    assert "dataset_version,started_at DESC" in text
    assert "dataset_version,created_at DESC" not in text


def test_0026_repairs_operational_schema_and_prefix_lookup():
    text = source("db/migrations/versions/0026_adaptive_operational_hotfix.py")
    assert "ADD COLUMN IF NOT EXISTS created_at" in text
    assert "varchar_pattern_ops" in text
    assert "adaptive_walk_forward_runs(profile_id,dataset_version,started_at DESC)" in text


def test_monitor_resolves_short_ids_and_is_user_scoped():
    text = source("signalrank_telegram/bot.py")
    assert "resolve_signal_reference(" in text
    assert "telegram_user_id == int(telegram_user_id)" in text
    assert "SignalDelivery.sent_ok.is_(True)" in text
    assert "resolved_payload = await _load_signal_payload" in text


def test_adaptive_remains_additive_to_legacy_strategy_groups():
    text = source("strategies/__init__.py")
    assert 'if "trend" in groups' in text
    assert 'if "momentum" in groups' in text
    assert 'if "volatility" in groups' in text
    assert 'if "structure" in groups' in text
    assert "ADAPTIVE ASSET-SPECIFIC STRATEGY INTELLIGENCE" in text
    assert "signals = adaptive_service.apply_to_signals(signals, adaptive_assessment)" in text


def test_resend_uses_round_robin_for_multi_user_batches():
    text = source("signalrank_telegram/bot.py")
    assert "[resend] audience round_robin" in text
    assert "ordered_others[start:] + ordered_others[:start]" in text


def test_websocket_circuit_uses_full_cooldown():
    text = source("data/ws_ingest.py")
    assert "asyncio.sleep(cool_down)" in text
    assert "asyncio.sleep(min(cool_down, max_backoff_s))" not in text


def test_tradingview_has_cache_and_rate_limit_circuit():
    text = source("strategies/tradingview.py")
    assert "TRADINGVIEW_CACHE_TTL_SECONDS" in text
    assert "TRADINGVIEW_RATE_LIMIT_COOLDOWN_SECONDS" in text
    assert '_open_circuit("rate_limit_exhausted")' in text


def test_macro_policy_requires_daily_context_only():
    from engine.timeframe_policy import resolve_required_timeframes

    req = resolve_required_timeframes("macro", trading_style="day")
    assert req.required == ("1d",)
    assert "1h" in req.optional


def test_bollinger_width_is_derived_from_nested_bands():
    from data.indicator_schema import normalize_indicator_schema

    indicators = {"bollinger": {"upper": 110.0, "lower": 90.0, "middle": 100.0}}
    out = normalize_indicator_schema(indicators)
    assert round(float(out["bollinger_width"]), 6) == 0.2
    assert round(float(out["bollinger"]["width"]), 6) == 0.2


def test_version_bumped():
    assert 'default="1.2.1"' in source("core/version.py")

def test_delivery_freshness_has_one_canonical_entry_drift_gate():
    source = Path("engine/delivery_freshness.py").read_text(encoding="utf-8")
    assert "def _canonical_entry_drift_pct" in source
    assert "entry_drift_exceeded:" not in source
    assert "final_entry_drift:" in source


def test_outcome_lookup_is_user_scoped_and_canonicalised():
    source = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    assert "_load_signal_payload(raw, telegram_user_id=uid)" in source
    assert "_read_cached_outcome_snapshot(_canonical_ref)" in source
    assert 'label="telegram.check_outcome"' in source

