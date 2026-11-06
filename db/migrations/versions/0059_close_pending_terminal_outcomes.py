"""Give closed outcomes stored with ``canonical_outcome='pending'`` their result.

Production, 4 Nov 2026 (daily review): ZECUSDT 5m long ``66b151e6`` was
delivered to five users and hit its stop on the 04:25 candle. The bot's
candle-scan path wrote ``status=sl``, ``r=-1`` through ``upsert_outcome``
without a canonical outcome, so the pending projection's
``canonical_outcome='pending'`` stayed; ``services.performance_ledger`` reads
the canonical outcome first and counted the loss as open. ``ca78f6f`` fixed new
writes; this migration corrects the rows already stored that way.

Data only, nothing deleted. Terminal rows are protected by
``trg_terminal_outcome_finality``, so each change is an audited correction
(``corrected_at/by/reason``; the reason names the previous value). The mapping
is ``db.pg_features._derived_canonical_outcome``: tp/tp3/win -> win; sl/loss/
stop/stop_loss -> loss, or partial_win when ``meta.tp_hit_index`` > 0;
partial_win/partial_win_be -> partial_win; time_stop, missed_entry, expired
keep their name. Status, R, percent and inclusion are unchanged.

Downgrade restores ``pending`` on exactly these rows (again as an audited
correction), which would reintroduce the defect; it exists for chain symmetry.

Revision ID: 0059_close_pending_terminal
Revises: 0058_exclude_no_trade_outcomes
"""
from alembic import op

revision = "0059_close_pending_terminal"
down_revision = "0058_exclude_no_trade_outcomes"
branch_labels = None
depends_on = None

CORRECTED_BY = "migration_0059_close_pending_terminal"

DERIVED_SQL = """
CASE
    WHEN LOWER(BTRIM(status)) IN ('tp', 'tp3', 'win') THEN 'win'
    WHEN LOWER(BTRIM(status)) IN ('sl', 'loss', 'stop', 'stop_loss') THEN
        CASE WHEN COALESCE(meta::jsonb->>'tp_hit_index', '') ~ '^[0-9]+$'
                  AND (meta::jsonb->>'tp_hit_index')::int > 0
             THEN 'partial_win' ELSE 'loss' END
    WHEN LOWER(BTRIM(status)) IN ('partial_win', 'partial_win_be') THEN 'partial_win'
    WHEN LOWER(BTRIM(status)) IN ('time_stop', 'missed_entry', 'expired') THEN LOWER(BTRIM(status))
END
"""

UPGRADE_SQL = f"""
UPDATE outcomes
SET canonical_outcome = {DERIVED_SQL},
    correction_reason = COALESCE(NULLIF(BTRIM(correction_reason), '') || '; ', '')
        || 'migration 0059: closed status ' || LOWER(BTRIM(status))
        || ' was stored with canonical_outcome=' || COALESCE(NULLIF(BTRIM(canonical_outcome), ''), 'empty'),
    corrected_by = '{CORRECTED_BY}',
    corrected_at = NOW()
WHERE LOWER(BTRIM(COALESCE(canonical_outcome, ''))) IN ('', 'pending')
  AND LOWER(BTRIM(COALESCE(status, ''))) IN
      ('tp', 'tp3', 'win', 'sl', 'loss', 'stop', 'stop_loss', 'partial_win', 'partial_win_be',
       'time_stop', 'missed_entry', 'expired')
"""

DOWNGRADE_SQL = f"""
UPDATE outcomes
SET canonical_outcome = 'pending',
    correction_reason = correction_reason || '; downgrade 0059: canonical_outcome restored to pending',
    corrected_at = NOW()
WHERE corrected_by = '{CORRECTED_BY}'
  AND correction_reason LIKE '%migration 0059: closed status % was stored with canonical_outcome=pending%'
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
