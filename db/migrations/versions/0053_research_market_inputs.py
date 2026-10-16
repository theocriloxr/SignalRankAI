"""Preserve the normalized inputs actually observed by adaptive components.

Revision ID: 0053_research_market_inputs
Revises: 0052_research_dataset_snapshots
"""
from alembic import op

revision = "0053_research_market_inputs"
down_revision = "0052_research_dataset_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE research_market_inputs (
        content_hash VARCHAR(64) PRIMARY KEY CHECK(content_hash ~ '^[0-9a-f]{64}$'),
        format_version INTEGER NOT NULL CHECK(format_version=1),
        asset VARCHAR(128) NOT NULL,
        timeframe VARCHAR(128) NOT NULL,
        candle_count INTEGER NOT NULL CHECK(candle_count BETWEEN 0 AND 2000),
        captured_at TIMESTAMPTZ NOT NULL,
        payload JSONB NOT NULL CHECK(jsonb_typeof(payload)='object')
            CHECK(octet_length(payload::text)<=1048576),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("""CREATE TRIGGER research_market_inputs_immutable
        BEFORE UPDATE OR DELETE ON research_market_inputs
        FOR EACH ROW EXECUTE FUNCTION reject_research_evidence_mutation()""")
    op.execute("""CREATE TRIGGER research_market_inputs_no_truncate
        BEFORE TRUNCATE ON research_market_inputs
        FOR EACH STATEMENT EXECUTE FUNCTION reject_research_evidence_mutation()""")


def downgrade() -> None:
    raise RuntimeError("research_market_inputs_require_preserved_evidence_restore")
