"""Add the profile/signal lookup used by bounded strategy-health surveillance.

Revision ID: 0050_profile_health_index
Revises: 0049_research_trial_ledger
"""
from alembic import op
from sqlalchemy import text
from db.profile_health_schema import PROFILE_HEALTH_INDEX_SQL, profile_health_index_definition_matches

revision = "0050_profile_health_index"
down_revision = "0049_research_trial_ledger"
branch_labels = None
depends_on = None

CREATE_SQL = "CREATE INDEX CONCURRENTLY ix_adaptive_evidence_profile_signal ON public.adaptive_signal_evidence (profile_id,signal_id)"


def _existing_index():
    raw = op.get_bind().execute(text(PROFILE_HEALTH_INDEX_SQL)).mappings().one_or_none()
    row = dict(raw) if raw is not None else None
    if row is not None and not profile_health_index_definition_matches(row):
        raise RuntimeError("profile_health_index_name_collision_or_definition_mismatch")
    return row


def upgrade() -> None:
    # Concurrent builds must run outside a transaction. Alembic commits earlier
    # revisions before this block; only this index is changed here.
    with op.get_context().autocommit_block():
        if op.get_context().as_sql:
            op.execute(CREATE_SQL)
            return
        existing = _existing_index()
        if existing is not None and existing["indisvalid"] and existing["indisready"]:
            return
        if existing is not None:
            # A cancelled concurrent build can leave an unusable index. Repair
            # only the verified nonunique index on the expected relation/keys.
            op.execute("DROP INDEX CONCURRENTLY public.ix_adaptive_evidence_profile_signal")
        op.execute(CREATE_SQL)
        created = _existing_index()
        if created is None or not created["indisvalid"] or not created["indisready"]:
            raise RuntimeError("profile_health_index_build_not_valid")


def downgrade() -> None:
    raise RuntimeError("profile_health_index_requires_forward_repair")
