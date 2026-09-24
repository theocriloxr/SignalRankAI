"""web-first signup acquisition and referral attribution

Revision ID: 0039_web_signup_acquisition
Revises: 0038_account_security_product
"""
from __future__ import annotations

from alembic import op

revision = "0039_web_signup_acquisition"
down_revision = "0038_account_security_product"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_acquisition (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            signup_channel VARCHAR(32) NOT NULL DEFAULT 'unknown',
            signup_origin VARCHAR(255),
            landing_path VARCHAR(512),
            http_referrer VARCHAR(1024),
            referral_code VARCHAR(64),
            utm_source VARCHAR(160),
            utm_medium VARCHAR(160),
            utm_campaign VARCHAR(200),
            utm_content VARCHAR(200),
            utm_term VARCHAR(200),
            client_type VARCHAR(24),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_acquisition_channel ON user_acquisition(signup_channel,created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_acquisition_referral ON user_acquisition(referral_code) WHERE referral_code IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_acquisition_utm_campaign ON user_acquisition(utm_campaign) WHERE utm_campaign IS NOT NULL")


def downgrade() -> None:
    # Acquisition evidence is intentionally retained.
    pass
