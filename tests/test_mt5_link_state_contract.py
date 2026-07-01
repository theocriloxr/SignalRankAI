from pathlib import Path


def test_mt5_link_status_distinguishes_saved_credentials_from_execution_ready():
    source = (Path(__file__).resolve().parents[1] / "services" / "mt5_client.py").read_text(encoding="utf-8")

    assert "get_user_mt5_link_status" in source
    assert '"linked": False' in source
    assert '"executable": False' in source
    assert 'status["executable"] = bool(found[2])' in source
    assert "ensure_user_mt5_account_id" in source
    assert "if status[\"linked\"] and not status[\"executable\"]" in source


def test_trading_mode_falls_back_to_mt5_credentials_table():
    source = (Path(__file__).resolve().parents[1] / "services" / "trading_mode_manager.py").read_text(encoding="utf-8")

    assert "get_user_mt5_account_id" in source
    assert "No executable MT5 account is ready" in source
