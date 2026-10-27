"""Bound pending ML-shadow observation cost without blocking decision writes.

Revision ID: 0054_shadow_pending_index
Revises: 0053_research_market_inputs
"""
from alembic import op

revision = "0054_shadow_pending_index"
down_revision = "0053_research_market_inputs"
branch_labels = None
depends_on = None

INDEX = "ix_decision_log_ml_pending_created"
CREATE_SQL = """CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_decision_log_ml_pending_created
    ON decision_log (created_at)
    WHERE decision='rejected' AND meta->>'layer'='ml'
      AND meta->>'outcome_tracked_at' IS NULL"""
VALIDATE_SQL = """DO $shadow_index$
DECLARE index_state RECORD;
BEGIN
    SELECT i.indisvalid,i.indisready,i.indnkeyatts,a.amname,
        pg_get_indexdef(i.indexrelid,1,true) AS column_name,
        regexp_replace(pg_get_expr(i.indpred,i.indrelid),'::text|[()[:space:]]','','g') AS predicate
    INTO index_state
    FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
        JOIN pg_am a ON a.oid=c.relam
    WHERE i.indrelid='decision_log'::regclass AND c.relname='ix_decision_log_ml_pending_created';
    IF NOT FOUND OR NOT index_state.indisvalid OR NOT index_state.indisready
        OR index_state.indnkeyatts<>1 OR index_state.amname<>'btree'
        OR index_state.column_name<>'created_at'
        OR index_state.predicate IS DISTINCT FROM
            'decision=''rejected''ANDmeta->>''layer''=''ml''ANDmeta->>''outcome_tracked_at''ISNULL'
    THEN RAISE EXCEPTION 'shadow_pending_index_invalid_or_definition_mismatch';
    END IF;
END; $shadow_index$"""


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(CREATE_SQL)
        # A failed concurrent build leaves an invalid index behind. IF NOT EXISTS
        # alone must never claim that such an index provides query protection.
        # Server-side validation also survives Alembic's offline SQL rendering.
        op.execute(VALIDATE_SQL)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_decision_log_ml_pending_created")
