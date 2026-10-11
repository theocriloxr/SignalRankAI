"""Immutable delivery baselines, predefined conditions and health evidence.

Revision ID: 0051_strategy_health_baselines
Revises: 0050_profile_health_index
"""
from alembic import op

revision = "0051_strategy_health_baselines"
down_revision = "0050_profile_health_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE strategy_health_baselines (
        baseline_id VARCHAR(64) PRIMARY KEY,
        profile_id VARCHAR(128) NOT NULL UNIQUE REFERENCES adaptive_asset_profiles(profile_id),
        profile_version INTEGER NOT NULL CHECK(profile_version > 0),
        profile_hash VARCHAR(64) NOT NULL,
        evidence_scope VARCHAR(64) NOT NULL CHECK(evidence_scope='confirmed_signal_delivery_outcomes'),
        approved_by BIGINT NOT NULL CHECK(approved_by > 0),
        approved_at TIMESTAMP NOT NULL DEFAULT NOW(),
        conditions_version VARCHAR(64) NOT NULL,
        payload JSONB NOT NULL CHECK(jsonb_typeof(payload)='object'),
        content_hash VARCHAR(64) NOT NULL
    )""")
    op.execute("""CREATE TABLE strategy_health_events (
        event_id BIGSERIAL PRIMARY KEY,
        profile_id VARCHAR(128) NOT NULL REFERENCES adaptive_asset_profiles(profile_id),
        baseline_id VARCHAR(64) REFERENCES strategy_health_baselines(baseline_id),
        event_hash VARCHAR(64) NOT NULL UNIQUE,
        report JSONB NOT NULL CHECK(jsonb_typeof(report)='object'),
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("CREATE INDEX ix_strategy_health_events_profile ON strategy_health_events(profile_id,event_id DESC)")
    for table in ("strategy_health_baselines", "strategy_health_events"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_research_evidence_mutation()")
        op.execute(f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION reject_research_evidence_mutation()")


def downgrade() -> None:
    raise RuntimeError("strategy_health_history_requires_preserved_evidence_restore")
