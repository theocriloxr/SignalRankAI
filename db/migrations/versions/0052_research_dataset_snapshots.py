"""Preserve the actual outcome rows consumed by adaptive research.

Revision ID: 0052_research_dataset_snapshots
Revises: 0051_strategy_health_baselines
"""
from alembic import op

revision = "0052_research_dataset_snapshots"
down_revision = "0051_strategy_health_baselines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE research_dataset_snapshots (
        dataset_version VARCHAR(128) PRIMARY KEY
            REFERENCES adaptive_dataset_versions(dataset_version),
        content_hash VARCHAR(64) NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),
        format_version INTEGER NOT NULL CHECK(format_version=1),
        row_count INTEGER NOT NULL CHECK(row_count BETWEEN 0 AND 100000),
        observation_cutoff TIMESTAMPTZ NOT NULL,
        payload JSONB NOT NULL CHECK(jsonb_typeof(payload)='object')
            CHECK(octet_length(payload::text)<=67108864),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("""CREATE TRIGGER research_dataset_snapshots_immutable
        BEFORE UPDATE OR DELETE ON research_dataset_snapshots
        FOR EACH ROW EXECUTE FUNCTION reject_research_evidence_mutation()""")
    op.execute("""CREATE TRIGGER research_dataset_snapshots_no_truncate
        BEFORE TRUNCATE ON research_dataset_snapshots
        FOR EACH STATEMENT EXECUTE FUNCTION reject_research_evidence_mutation()""")


def downgrade() -> None:
    raise RuntimeError("research_dataset_snapshots_require_preserved_evidence_restore")
