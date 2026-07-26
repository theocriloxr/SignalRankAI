from pathlib import Path


def test_railway_simulation_is_safe_and_exercises_real_entrypoint():
    source = Path("scripts/simulate_railway.py").read_text(encoding="utf-8")
    assert '"railway_main:app"' in source
    assert '"AUTO_TRADE_ENABLED": "0"' in source
    assert '"COPY_TRADE_ENABLED": "0"' in source
    assert '"REAL_PAYOUTS_ENABLED": "0"' in source
    assert '"PAYMENTS_PUBLIC_ENABLED": "0"' in source
    assert 'base + "/healthz"' in source
    assert 'base + "/telegram/webhook"' in source


def test_migration_failure_is_fail_closed_when_boot_migration_enabled():
    source = Path("start.sh").read_text(encoding="utf-8")
    assert "Migration failed; refusing to start" in source
    assert 'exit 1' in source


def test_procfile_web_matches_railway_monolith():
    source = Path("Procfile").read_text(encoding="utf-8")
    assert "web: uvicorn railway_main:app" in source


def test_start_script_is_fail_fast_and_single_worker():
    source = Path("start.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in source
    assert "--workers 1" in source
    assert "exec uvicorn railway_main:app" in source


def test_railway_healthcheck_timeout_allows_cold_start():
    import json

    config = json.loads(Path("railway.json").read_text(encoding="utf-8"))
    assert config["deploy"]["healthcheckPath"] == "/healthz"
    assert config["deploy"]["healthcheckTimeout"] >= 300


def test_railway_simulation_accepts_canonical_liveness_status():
    source = Path("scripts/simulate_railway.py").read_text(encoding="utf-8")
    assert '{"ok", "healthy", "degraded"}' in source


def test_railway_simulation_authenticates_webhook_request():
    source = Path("scripts/simulate_railway.py").read_text(encoding="utf-8")
    assert "X-Telegram-Bot-Api-Secret-Token" in source
    assert 'env.get("TELEGRAM_WEBHOOK_SECRET")' in source
