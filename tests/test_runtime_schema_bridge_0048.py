from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_0048_bridges_legacy_runtime_columns_into_canonical_chain() -> None:
    migration = (ROOT / "db/migrations/versions/0048_runtime_schema_bridge.py").read_text(encoding="utf-8")
    assert 'revision = "0048_runtime_schema_bridge"' in migration
    assert 'down_revision = "0047_event_outbox"' in migration

    required = (
        "accepted_terms BOOLEAN NOT NULL DEFAULT FALSE",
        "execution_mode VARCHAR(16) NOT NULL DEFAULT 'manual'",
        "auto_signals_daily_limit INTEGER NOT NULL DEFAULT 3",
        "status VARCHAR(16) NOT NULL DEFAULT 'issued'",
        "trade_profile VARCHAR(16)",
        "sent_ok BOOLEAN NOT NULL DEFAULT FALSE",
        "generated_at_utc TIMESTAMP",
        "canonical_outcome VARCHAR(16)",
        "Base.metadata.create_all(bind=bind, checkfirst=True)",
    )
    for marker in required:
        assert marker in migration


def test_schema_admission_requires_0048_bridge_columns() -> None:
    audit = (ROOT / "scripts/assert_database_schema.py").read_text(encoding="utf-8")
    for marker in (
        "users_accepted_terms",
        "users_execution_mode",
        "signals_status",
        "signals_trade_profile",
        "signal_deliveries_sent_ok",
        "signal_deliveries_generated_at_utc",
        "outcomes_canonical_outcome",
    ):
        assert marker in audit


def test_release_chain_and_current_release_name_0048_as_head() -> None:
    verifier = (ROOT / "scripts/verify_release_chain.py").read_text(encoding="utf-8")
    release = (ROOT / "CURRENT_RELEASE.md").read_text(encoding="utf-8")
    assert 'EXPECTED_HEAD = os.getenv("EXPECTED_ALEMBIC_HEAD", "0051_strategy_health_baselines")' in verifier
    assert '"0047_event_outbox"' in verifier
    assert '"0048_runtime_schema_bridge"' in verifier
    assert "Repository Alembic head: 0051_strategy_health_baselines" in release
    assert "signalrank-blueprint-0048-runtime-schema-bridge-20261002" in release
