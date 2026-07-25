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
