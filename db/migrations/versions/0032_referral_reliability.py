"""canonical referral attribution and reward reliability

Revision ID: 0032_referral_reliability
Revises: 0031_perf_paper_reliability
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0032_referral_reliability"
down_revision = "0031_perf_paper_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS reference VARCHAR(128)")
    op.execute("ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_rewards_reference
        ON referral_rewards (reference)
        WHERE reference IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_referral_rewards_referrer_type_created
        ON referral_rewards (referrer_user_id, reward_type, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_referrals_referrer_created
        ON referrals (referrer_user_id, created_at)
    """)
    # Existing signup attributions are the canonical qualified-referral truth.
    # Mark them successful so legacy conversion-only queries cannot hide them.
    op.execute("""
        UPDATE referrals
        SET is_successful = TRUE,
            successful_at = COALESCE(successful_at, created_at)
        WHERE is_successful = FALSE
    """)
    # referral_count becomes a denormalized total, not a resettable progress bucket.
    op.execute("""
        UPDATE users u
        SET referral_count = counts.total
        FROM (
            SELECT referrer_user_id, COUNT(*)::integer AS total
            FROM referrals
            GROUP BY referrer_user_id
        ) counts
        WHERE u.id = counts.referrer_user_id
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_referrals_referrer_created")
    op.execute("DROP INDEX IF EXISTS ix_referral_rewards_referrer_type_created")
    op.execute("DROP INDEX IF EXISTS uq_referral_rewards_reference")
    op.execute("ALTER TABLE referral_rewards DROP COLUMN IF EXISTS meta")
    op.execute("ALTER TABLE referral_rewards DROP COLUMN IF EXISTS reference")
