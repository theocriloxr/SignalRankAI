from __future__ import annotations

import ast
from pathlib import Path

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db" / "migrations" / "versions" / "0031_performance_paper_reliability.py"


def test_migration_0031_execute_literals_have_no_accidental_bind_parameters() -> None:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    statements: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "op"
            and func.attr == "execute"
        ):
            continue
        value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            statements.append(value.value)

    assert statements
    accidental = {
        index: sorted(text(statement)._bindparams)
        for index, statement in enumerate(statements)
        if text(statement)._bindparams
    }
    assert accidental == {}


def test_migration_0031_legacy_attempt_id_uses_bind_safe_separator_and_cast() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "md5(pp.position_id || ':0031')" not in source
    assert "CAST(CAST(md5(pp.position_id || '|0031') AS uuid) AS text)" in source
