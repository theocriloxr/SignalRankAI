"""Exclude no-trade and degenerate outcomes from performance and learning.

Owner approval, 3 Nov 2026 (daily review). Production held 32 eligible
``missed_entry`` outcomes carrying an R-multiple (avg -1.84R, range -63R to
+40R): no position was opened, but a pending projection's provisional R
survived the terminal write (fixed in ``ae6e64a``). Outcomes with |R| > 10 come
from degenerate stops (June-July: NZDJPY 1d avg -37R, OPUSDT 5m -32R).

- missed_entry / missed / expired with an R: audited correction (the finality
  trigger requires corrected_at/by/reason); R and percent cleared; the original
  R is kept in correction_reason; excluded from performance.
- |R| > 10: R kept as recorded, excluded from performance with a reason.

Nothing is deleted. Downgrade restores eligibility of the degenerate rows; the
cleared R values stay in correction_reason for a manual audited restore.

Revision ID: 0058_exclude_no_trade_outcomes
Revises: 0057_expectancy_shadow_index
"""
from alembic import op

revision = "0058_exclude_no_trade_outcomes"
down_revision = "0057_expectancy_shadow_index"
branch_labels = None
depends_on = None

NO_TRADE_SQL = """
UPDATE outcomes
SET correction_reason = 'migration 0058: no position was opened (' || LOWER(status)
        || '); removed r_multiple=' || r_multiple::text
        || COALESCE(', percent=' || percent::text, ''),
    corrected_by = 'migration_0058_exclude_no_trade_outcomes',
    corrected_at = NOW(),
    provenance = 'audited_correction',
    r_multiple = NULL,
    percent = NULL,
    performance_inclusion_status = 'excluded',
    performance_exclusion_reason = 'no_trade_outcome_with_r'
WHERE r_multiple IS NOT NULL
  AND (LOWER(COALESCE(status, '')) IN ('missed_entry', 'missed', 'expired')
       OR LOWER(COALESCE(canonical_outcome, '')) IN ('missed_entry', 'missed', 'expired'))
"""

DEGENERATE_SQL = """
UPDATE outcomes
SET performance_inclusion_status = 'excluded',
    performance_exclusion_reason = 'degenerate_stop_abs_r_gt_10'
WHERE r_multiple IS NOT NULL
  AND ABS(r_multiple) > 10
  AND performance_inclusion_status = 'eligible'
"""


def upgrade() -> None:
    op.execute(NO_TRADE_SQL)
    op.execute(DEGENERATE_SQL)


def downgrade() -> None:
    op.execute(
        "UPDATE outcomes SET performance_inclusion_status = 'eligible', performance_exclusion_reason = NULL "
        "WHERE performance_exclusion_reason = 'degenerate_stop_abs_r_gt_10'"
    )
