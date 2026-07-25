from pathlib import Path


def test_required_diagnostic_commands_are_implemented_and_registered():
    commands = Path("signalrank_telegram/commands.py").read_text(encoding="utf-8")
    bot = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    required = (
        "why_no_signal",
        "delivery_eligibility",
        "ohlc_health",
        "asset_capability",
        "asset_class_test",
        "all_asset_test_status",
        "owner_test_delivery",
    )
    for name in required:
        assert f"async def {name}_command" in commands
        assert f'CommandHandler("{name}"' in bot


def test_owner_test_delivery_is_non_trading():
    source = Path("signalrank_telegram/commands.py").read_text(encoding="utf-8")
    start = source.index("async def owner_test_delivery_command")
    block = source[start : start + 4000]
    assert "TEST — NOT A TRADING SIGNAL" in block
    assert "affects_performance" in block
    assert "MT5" not in block
    assert "mark_signal_delivery_result" not in block


def test_no_signal_command_uses_recorded_pipeline_evidence():
    source = Path("signalrank_telegram/commands.py").read_text(encoding="utf-8")
    assert 'state.get_sync("engine:last_cycle")' in source
    assert "market_data_assets" in source
    assert "score_rejected" in source
    assert "risk_failed" in source
