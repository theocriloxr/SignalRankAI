"""Static guards for two database bug classes found on 29-30 Oct 2026.

1. A time-zone-aware datetime bound to a ``timestamp without time zone``
   column: asyncpg raises DataError, which callers mostly swallowed into empty
   reports (/proof, /strategies, owner /users, the drawdown breaker...).
2. An ORM row read after ``await session.rollback()``, which expires every
   loaded row: DetachedInstanceError once the session closes.

Both are invisible to tests with in-memory fakes, so the whole codebase is
scanned. Every other timestamp column is naive except the tables in
``AWARE_TABLES`` (checked against the live schema when PostgreSQL is available).
"""
from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AWARE_TABLES = {"event_outbox", "research_dataset_snapshots", "research_market_inputs"}
# Found and deliberately left unchanged: fixing it would let the job send
# automatic broker close orders, which needs the owner's approval.
OWNER_DECISION_PENDING = {("signalrank_telegram/bot.py", "smart_exit_guard_job")}


def _python_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.split() if not f.startswith(("tests/", "docs/", "tests_sdk/"))]


def _models() -> tuple[dict[str, str], set[tuple[str, str]]]:
    from sqlalchemy import DateTime

    import db.models  # noqa: F401
    from db.models import Base

    tables = {m.class_.__name__: m.local_table.name for m in Base.registry.mappers}
    naive = {(t.name, c.name) for t in Base.metadata.tables.values() for c in t.columns
             if isinstance(c.type, DateTime) and not c.type.timezone and t.name not in AWARE_TABLES}
    return tables, naive


def _aware(node, env) -> bool | None:
    """True for an aware datetime, False for naive, None when unknown."""
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        return _aware(node.left, env)
    if isinstance(node, ast.BoolOp):
        values = [_aware(v, env) for v in node.values]
        return True if True in values else None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        attr = node.func.attr
        if attr == "replace" and any(k.arg == "tzinfo" for k in node.keywords):
            value = next(k.value for k in node.keywords if k.arg == "tzinfo")
            return not (isinstance(value, ast.Constant) and value.value is None)
        if attr == "now" and isinstance(node.func.value, ast.Name) and node.func.value.id == "datetime":
            return bool(node.args or node.keywords)
        if attr == "astimezone":
            return bool(node.args)
    return None


def _enclosing_names(tree) -> dict[ast.AST, tuple[str, ...]]:
    """Each function's chain of enclosing function names, outermost first."""
    chains: dict[ast.AST, tuple[str, ...]] = {}

    def visit(node, chain):
        for child in ast.iter_child_nodes(node):
            child_chain = chain
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child_chain = (*chain, child.name)
                chains[child] = child_chain
            visit(child, child_chain)

    visit(tree, ())
    return chains


def _aware_naive_bindings() -> set[tuple[str, tuple[str, ...], int]]:
    tables, naive = _models()
    naive_names = {c for _, c in naive}
    hits: set[tuple[str, tuple[str, ...], int]] = set()
    for path in _python_files():
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        chains = _enclosing_names(tree)
        for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            env: dict[str, bool | None] = {}
            for node in sorted((n for n in ast.walk(fn) if isinstance(n, ast.Assign)), key=lambda n: n.lineno):
                kind = _aware(node.value, env)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        env[target.id] = kind if env.get(target.id, kind) == kind else None

            def hit(node):
                hits.add((path, chains[fn], node.lineno))

            for node in ast.walk(fn):
                if isinstance(node, ast.Compare):
                    sides = [node.left, *node.comparators]
                    for side in sides:
                        if (isinstance(side, ast.Attribute) and isinstance(side.value, ast.Name)
                                and (tables.get(side.value.id), side.attr) in naive
                                and any(_aware(o, env) is True for o in sides if o is not side)):
                            hit(node)
                elif isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id in tables:
                        if any(k.arg and (tables[func.id], k.arg) in naive and _aware(k.value, env) is True
                               for k in node.keywords):
                            hit(node)
                    elif isinstance(func, ast.Attribute) and func.attr == "values":
                        if any(k.arg in naive_names and _aware(k.value, env) is True for k in node.keywords):
                            hit(node)
                    elif isinstance(func, ast.Attribute) and func.attr == "execute" and len(node.args) >= 2 \
                            and isinstance(node.args[1], ast.Dict):
                        sql = " ".join(c.value for c in ast.walk(node.args[0])
                                       if isinstance(c, ast.Constant) and isinstance(c.value, str))
                        if not any(t in sql for t in AWARE_TABLES) and any(
                                _aware(v, env) is True for v in node.args[1].values):
                            hit(node)
                elif isinstance(node, ast.Assign) and _aware(node.value, env) is True:
                    for target in node.targets:
                        if (isinstance(target, ast.Attribute) and target.attr in naive_names
                                and not (isinstance(target.value, ast.Name) and target.value.id == "self")):
                            hit(node)
    return hits


ROW_CALLS = {"scalar_one_or_none", "scalar_one", "scalars", "first", "one", "one_or_none"}


def _session_rows(fn) -> dict[str, int]:
    """Names bound to ORM rows loaded through session.execute(...).scalar*/first or session.get(...)."""
    rows: dict[str, int] = {}
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        top = node.value.value if isinstance(node.value, ast.Await) else node.value
        if not (isinstance(top, ast.Call) and isinstance(top.func, ast.Attribute)):
            continue  # wrapped (dict(...), _mapping(...)) or not a call: not a live row
        names = {c.func.attr for c in ast.walk(top) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
        loads = (top.func.attr in ROW_CALLS | {"all"} and "execute" in names and "mappings" not in names
                 and (top.func.attr != "all" or "scalars" in names)) or (
            top.func.attr == "get" and isinstance(top.func.value, ast.Name) and "session" in top.func.value.id)
        if loads:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    rows[target.id] = node.lineno
    return rows


def _reads_after_rollback() -> set[tuple[str, str, int]]:
    hits: set[tuple[str, str, int]] = set()
    for path in _python_files():
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)):
            rows = _session_rows(fn)
            if not rows:
                continue
            for stmt in ast.walk(fn):
                if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await)
                        and isinstance(stmt.value.value, ast.Call)
                        and getattr(stmt.value.value.func, "attr", "") == "rollback"):
                    continue
                cursor, in_handler = stmt, False
                while cursor in parents and cursor is not fn:
                    cursor = parents[cursor]
                    in_handler = in_handler or isinstance(cursor, ast.ExceptHandler)
                if in_handler:
                    continue
                block = next((getattr(parents[stmt], f) for f in ("body", "orelse", "finalbody")
                              if stmt in getattr(parents[stmt], f, [])), [])
                rest = block[block.index(stmt) + 1:]
                scope = ([n for s in rest for n in ast.walk(s)]
                         if any(isinstance(s, (ast.Return, ast.Raise, ast.Continue, ast.Break)) for s in rest)
                         else [n for n in ast.walk(fn) if getattr(n, "lineno", 0) > stmt.lineno])
                expunged = {a.id for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "expunge"
                            and c.lineno < stmt.lineno for a in c.args if isinstance(a, ast.Name)}
                live = {name for name, line in rows.items() if line < stmt.lineno and name not in expunged}
                for node in scope:
                    used = None
                    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and isinstance(node.ctx, ast.Load):
                        used = node.value.id
                    elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "getattr" and node.args \
                            and isinstance(node.args[0], ast.Name):
                        used = node.args[0].id
                    if used in live:
                        hits.add((path, fn.name, node.lineno))
    return hits


def test_no_aware_datetime_is_bound_to_a_naive_column():
    hits = _aware_naive_bindings()
    pending = {(p, name) for p, chain, _ in hits for name in chain if (p, name) in OWNER_DECISION_PENDING}
    unexpected = sorted(h for h in hits if not any((h[0], name) in OWNER_DECISION_PENDING for name in h[1]))
    assert not unexpected, "bind naive UTC (datetime.now(timezone.utc).replace(tzinfo=None)):\n" + "\n".join(
        f"{p}:{line} in {'.'.join(chain)}" for p, chain, line in unexpected)
    assert pending == OWNER_DECISION_PENDING, "a pending site was fixed: remove it from OWNER_DECISION_PENDING"


def test_no_orm_row_is_read_after_rollback():
    hits = sorted(_reads_after_rollback())
    assert not hits, "copy the values before session.rollback():\n" + "\n".join(f"{p}:{line} in {fn}" for p, fn, line in hits)


@pytest.mark.asyncio
async def test_only_the_listed_tables_have_time_zone_aware_columns():
    url = os.getenv("DATABASE_URL", "")
    if "postgresql" not in url or os.getenv("APP_ENV") != "test":
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    from sqlalchemy import text

    from db.session import dispose_engine_for_event_loop, get_session

    async with get_session() as session:
        aware = {row[0] for row in await session.execute(text(
            "SELECT DISTINCT table_name FROM information_schema.columns "
            "WHERE table_schema='public' AND data_type='timestamp with time zone'"))}
        await session.rollback()
    await dispose_engine_for_event_loop()
    assert aware == AWARE_TABLES
