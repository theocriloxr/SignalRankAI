from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]


def _render_upgrade_sql() -> str:
    env = os.environ.copy()
    env["DATABASE_MIGRATION_URL"] = "postgresql+psycopg2://audit:audit@localhost/audit"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_v104_is_the_sole_migration_head() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert script.get_heads() == ["0034_production_integrity"]


def test_clean_upgrade_contains_all_signal_runtime_columns_before_head() -> None:
    sql = _render_upgrade_sql().lower()
    assert "add column if not exists mfe_pct double precision" in sql
    assert "add column if not exists mae_pct double precision" in sql
    assert "performance_version integer not null default 2" in sql
    assert "create unique index ix_signals_active_thesis" in sql


def test_schema_audit_checks_signal_orm_contract() -> None:
    from scripts.schema_audit import audit_signal_runtime_contract

    result = audit_signal_runtime_contract(ROOT)
    assert result["ok"] is True
    assert result["missing_columns"] == []
    assert result["active_guard_sql"] is True


def test_diagnostics_uses_catalog_semantics_not_fragile_index_text() -> None:
    source = (ROOT / "scripts" / "deployment_diagnostics.py").read_text(encoding="utf-8")
    assert "pg_get_expr(i.indpred, i.indrelid)" in source
    assert "signal_runtime_columns" in source
    assert "%WHERE (status = ''active''::text)%" not in source


def test_readiness_requires_signal_metrics_and_active_guard() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    for name in ("signals.mfe_pct", "signals.mae_pct", "signals.performance_version"):
        assert name in source
    assert "active_signal_guard_missing" in source
    assert "[readyz] degraded checks=%s" in source
