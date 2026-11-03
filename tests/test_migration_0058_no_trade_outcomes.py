"""Migration 0058 (owner approval, 3 Nov 2026): exclude no-trade and degenerate outcomes.

Verified on a scratch PostgreSQL 16 migrated from empty to 0057 with seeded
outcomes (finality trigger active): missed_entry/expired rows with an R get an
audited correction and are excluded; |R| > 10 rows are excluded with R kept;
normal losses and missed entries without an R are untouched; downgrade then
re-upgrade is stable.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "db" / "migrations" / "versions" / "0058_exclude_no_trade_and_degenerate_outcomes.py"


def _module():
    spec = importlib.util.spec_from_file_location("m0058", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain():
    m = _module()
    assert m.revision == "0058_exclude_no_trade_outcomes"
    assert m.down_revision == "0057_expectancy_shadow_index"
    assert len(m.revision) <= 32  # alembic_version.version_num


def test_no_trade_rows_use_audited_correction_and_keep_the_original_r():
    sql = _module().NO_TRADE_SQL
    for column in ("corrected_by", "corrected_at", "correction_reason"):
        assert column in sql  # required by trg_terminal_outcome_finality
    assert "r_multiple::text" in sql
    assert "r_multiple = NULL" in sql and "percent = NULL" in sql
    assert "WHERE r_multiple IS NOT NULL" in sql
    assert "('missed_entry', 'missed', 'expired')" in sql
    assert "DELETE" not in sql.upper()


def test_degenerate_rows_are_excluded_not_rewritten():
    sql = _module().DEGENERATE_SQL
    assert "ABS(r_multiple) > 10" in sql
    assert "r_multiple =" not in sql
    assert "performance_exclusion_reason = 'degenerate_stop_abs_r_gt_10'" in sql
