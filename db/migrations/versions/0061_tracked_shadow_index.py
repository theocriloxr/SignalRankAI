"""Index the decision-log rows that carry a tracked outcome (9 Nov 2026).

Bottleneck: the strategy scorecard rebuild (every 3 h) read ~2 M decision_log
rows in id pages and kept the ~18% with ``meta->>'outcome_tracked_at'``; it took
385 s and held an analytics DB slot that the adaptive monitor then waited for.
A partial index on ``id`` for tracked rows lets each page read only those rows.

Built CONCURRENTLY, so decision writes are never blocked; a failed build is
detected and reported instead of leaving an invalid index. Index only; no data
changes.

Revision ID: 0061_tracked_shadow_index
Revises: 0060_notification_channels
"""
from alembic import op

revision = "0061_tracked_shadow_index"
down_revision = "0060_notification_channels"
branch_labels = None
depends_on = None

CREATE_SQL = """CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_decision_log_tracked_id
    ON decision_log (id)
    WHERE meta->>'outcome_tracked_at' IS NOT NULL"""
VALIDATE_SQL = """DO $tracked_index$
DECLARE index_state RECORD;
BEGIN
    SELECT i.indisvalid,i.indisready,i.indnkeyatts,a.amname,
        pg_get_indexdef(i.indexrelid,1,true) AS column_name,
        regexp_replace(pg_get_expr(i.indpred,i.indrelid),'::text|[()[:space:]]','','g') AS predicate
    INTO index_state
    FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
        JOIN pg_am a ON a.oid=c.relam
    WHERE i.indrelid='decision_log'::regclass AND c.relname='ix_decision_log_tracked_id';
    IF NOT FOUND OR NOT index_state.indisvalid OR NOT index_state.indisready
        OR index_state.indnkeyatts<>1 OR index_state.amname<>'btree'
        OR index_state.column_name<>'id'
        OR index_state.predicate IS DISTINCT FROM 'meta->>''outcome_tracked_at''ISNOTNULL'
    THEN RAISE EXCEPTION 'tracked_shadow_index_invalid_or_definition_mismatch';
    END IF;
END; $tracked_index$"""


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(CREATE_SQL)
        op.execute(VALIDATE_SQL)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_decision_log_tracked_id")
