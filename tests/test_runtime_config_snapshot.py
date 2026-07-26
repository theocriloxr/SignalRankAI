from pathlib import Path

from scripts.runtime_config_snapshot import build_snapshot, parse_env_file, redact_values, validate_config


def test_owner_beta_profile_passes_hard_errors():
    path = Path("configs/env/railway-hobby-owner-beta.env.example")
    snapshot = build_snapshot(path)
    assert snapshot.valid is True
    assert not [item for item in snapshot.findings if item["level"] == "error"]


def test_production_testing_and_execution_conflicts_fail():
    values = parse_env_file(Path("configs/env/railway-hobby-owner-beta.env.example"))
    values.update(
        {
            "PUBLIC_TESTING_MODE": "1",
            "AUTO_TRADE_ENABLED": "1",
            "REAL_EXECUTION_ENABLED": "0",
            "UVICORN_WORKERS": "2",
            "DB_POOL_SIZE": "10",
        }
    )
    codes = {finding.code for finding in validate_config(values, profile_name="test") if finding.level == "error"}
    assert {"production_public_testing", "execution_gate", "worker_count", "db_pool_cap"}.issubset(codes)


def test_redaction_never_emits_secret_values():
    redacted = redact_values({
        "TELEGRAM_BOT_TOKEN": "secret-token",
        "DATABASE_URL": "postgres://secret",
        "ENGINE_UNIVERSE_CAP": "18",
    })
    assert redacted["TELEGRAM_BOT_TOKEN"] == "<configured>"
    assert redacted["DATABASE_URL"] == "<configured>"
    assert redacted["ENGINE_UNIVERSE_CAP"] == "18"
