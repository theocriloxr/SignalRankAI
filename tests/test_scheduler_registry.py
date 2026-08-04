"""Scheduler and worker registry parity tests (Phase 18).

Every legitimate job must run in both staging and production against the
matching environment's resources, with exactly one owner per singleton job,
idempotent restarts and non-overlapping executions (max_instances=1).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _scheduler_jobs(source: str) -> list[dict[str, object]]:
    """AST-extract add_job(..., id=..., max_instances=..., trigger) calls."""
    tree = ast.parse(source, filename="scheduler.py")
    jobs: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_job"):
            continue
        trigger = None
        job_id = None
        max_instances = None
        replace_existing = None
        for keyword in node.keywords:
            if keyword.arg == "id" and isinstance(keyword.value, ast.Constant):
                job_id = keyword.value.value
            elif keyword.arg == "max_instances" and isinstance(keyword.value, ast.Constant):
                max_instances = keyword.value.value
            elif keyword.arg == "replace_existing" and isinstance(keyword.value, ast.Constant):
                replace_existing = keyword.value.value
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            trigger = node.args[1].value
        elif len(node.args) == 1 and isinstance(node.args[0], ast.Constant):
            trigger = node.args[0].value
        jobs.append(
            {
                "id": job_id,
                "trigger": trigger,
                "max_instances": max_instances,
                "replace_existing": replace_existing,
            }
        )
    return jobs


def _bot_jobs() -> list[dict[str, object]]:
    return _scheduler_jobs((ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8-sig"))


def _exclusive_registration_ids(source: str) -> set[str]:
    """Job ids registered in both an if branch and its else branch.

    Scheduler registrations are often split across ``if _minimal_scheduler_mode``
    / ``else`` branches that are mutually exclusive at runtime; each job must
    count once across the pair.
    """
    tree = ast.parse(source, filename="scheduler.py")
    exclusive: set[str] = set()

    def _collect(stmts: list[ast.stmt]) -> set[str]:
        out: set[str] = set()
        for stmt in stmts:
            for sub in ast.walk(stmt):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "add_job"
                ):
                    for keyword in sub.keywords:
                        if keyword.arg == "id" and isinstance(keyword.value, ast.Constant):
                            out.add(str(keyword.value.value))
        return out

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        body_ids = _collect(node.body)
        orelse_ids = _collect(node.orelse)
        exclusive |= (body_ids & orelse_ids)
    return exclusive


def test_scheduler_jobs_have_unique_ids() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8-sig")
    jobs = _scheduler_jobs(source)
    ids = [str(job["id"]) for job in jobs if job["id"] is not None]
    assert ids, "no scheduler.add_job registrations found in bot.py"
    exclusive = _exclusive_registration_ids(source)
    # Deduplicate mutually-exclusive if/else pairs before checking uniqueness.
    effective: list[str] = []
    seen: set[str] = set()
    for job_id in ids:
        if job_id in exclusive:
            if job_id in seen:
                continue
        seen.add(job_id)
        effective.append(job_id)
    duplicates = sorted({job_id for job_id in effective if effective.count(job_id) > 1})
    assert not duplicates, f"duplicate scheduler job ids: {duplicates}"


def test_scheduler_jobs_never_overlap() -> None:
    jobs = [job for job in _bot_jobs() if job["id"] is not None]
    non_serial = [
        str(job["id"])
        for job in jobs
        if job["max_instances"] not in (1, None) or (job["max_instances"] is None and job["replace_existing"] is not True)
    ]
    # Every registered job must be serial (max_instances=1). Jobs registered
    # without an explicit max_instances must use replace_existing=True so a
    # redeploy cannot stack duplicate executions.
    assert not non_serial, f"scheduler jobs missing serialisation guard: {non_serial}"


def _worker_task_names(source: str) -> set[str]:
    """AST-extract ``_register_task("name", ...)`` call names from the worker.

    Matches both a plain ``_register_task("name", ...)`` call (Name) and any
    ``self._register_task("name", ...)`` style call (Attribute).
    """
    tree = ast.parse(source, filename="worker.py")
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_register_task = (
            isinstance(func, ast.Name) and func.id == "_register_task"
        ) or (isinstance(func, ast.Attribute) and func.attr == "_register_task")
        if not is_register_task:
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            names.add(str(node.args[0].value))
    return names


def test_critical_jobs_are_owned_by_single_service() -> None:
    """Core singleton jobs must not be owned by both the bot and the worker.

    The bot registers scheduler jobs via ``add_job(..., id=...)`` while the
    worker registers loops via ``_register_task("name", ...)``. A job that
    appears in both files risks dual ownership and duplicated side effects.
    """
    bot_source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8-sig")
    worker_source = (ROOT / "worker" / "worker.py").read_text(encoding="utf-8-sig")
    bot_jobs = {str(job["id"]) for job in _scheduler_jobs(bot_source) if job["id"]}
    worker_tasks = _worker_task_names(worker_source)
    assert bot_jobs, "no scheduler job ids found in bot.py"
    assert worker_tasks, "no worker task names found in worker.py"
    overlap = sorted(bot_jobs & worker_tasks)
    # Loops that are deliberately started by both services as long as a runtime
    # lease/ownership lock keeps a single active owner may stay in the allowlist.
    allowed_shared = {"resend_unsent_signals", "realtime_outcomes", "outcome_projection"}
    unexpected = [job_id for job_id in overlap if job_id not in allowed_shared]
    assert not unexpected, f"singleton jobs owned by multiple services: {unexpected}"


def test_worker_register_task_names_are_unique() -> None:
    """Worker _register_task names must be unique within the worker."""
    source = (ROOT / "worker" / "worker.py").read_text(encoding="utf-8")
    import re

    names = re.findall(r'_register_task\(\s*"([^"]+)"', source)
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"duplicate worker task names: {duplicates}"
    assert names, "no worker tasks registered"


def test_resend_job_is_budgeted_and_lease_guarded() -> None:
    """The resend job must have a timeout budget and a cross-replica lease."""
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8-sig")
    assert "acquire_scheduler_job_lease" in source
    assert "RESEND_JOB_TIMEOUT_SECONDS" in source or "job_timeout" in source
    assert "RESEND_JOB_LEASE_SECONDS" in source
