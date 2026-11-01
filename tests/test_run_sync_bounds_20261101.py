"""Every blocking run_sync() call has a time limit (1 Nov 2026).

run_sync() without a timeout waits forever. A database call on a dead
connection once held the engine for six days; a scheduler job (max_instances=1)
that hangs never runs again until restart. All 117 unbounded calls were
reviewed one by one: 55 now pass a timeout, the rest are bounded inside the
coroutine or listed below with the reason they stay as they are.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (file, enclosing function) -> why it has no outer timeout
UNBOUNDED_BY_DESIGN = {
    ("engine/loop.py", "start_engine_loop"): "the engine loop runs for the life of the process",
    ("ml/train_model.py", "<module>"): "command-line entry point",
    ("scripts/purge_excluded_signals.py", "<module>"): "command-line entry point",
    ("scripts/test_run_sync.py", "<module>"): "manual diagnostic script",
    ("engine/core.py", "_refresh_runtime_thresholds"): "fallback branch for a run_sync without a timeout parameter",
}
# Left unchanged pending an owner decision: these jobs place or cancel broker
# orders or switch execution modes, so a cut-off run changes real-money behaviour.
OWNER_DECISION_PENDING = {
    ("signalrank_telegram/bot.py", "_auto_execute_signal_if_enabled"),
    ("signalrank_telegram/bot.py", "run_bot.smart_exit_guard_job"),
    ("signalrank_telegram/bot.py", "run_bot.drawdown_circuit_breaker_job"),
    ("signalrank_telegram/bot.py", "run_bot.killswitch_close_all_watchdog_job"),
    # Passes a function, not a coroutine, after a failing import: the ATR stop
    # repair has never run; fixing it changes generated stops and targets.
    ("engine/signal_controller.py", "SignalController._normalize_signal"),
}


def _unbounded_calls() -> set[tuple[str, str, int]]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    hits: set[tuple[str, str, int]] = set()
    for path in out.split():
        if path.startswith(("tests/", "docs/", "tests_sdk/")):
            continue
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        chains: dict[ast.AST, str] = {}

        def visit(node, chain):
            for child in ast.iter_child_nodes(node):
                child_chain = chain
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    child_chain = (*chain, child.name)
                chains[child] = ".".join(child_chain) or "<module>"
                visit(child, child_chain)

        visit(tree, ())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name not in {"run_sync", "_run_sync"} and not (name.startswith("_run") and name.endswith("sync")):
                continue
            if isinstance(func, ast.Attribute) and getattr(func.value, "id", "") != "async_runner":
                continue  # SQLAlchemy's conn.run_sync(fn) runs fn inline and forwards keywords to it
            if any(k.arg == "timeout" for k in node.keywords) or len(node.args) >= 2 or not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Call):
                inner = arg.func
                # asyncio.sleep(...) / asyncio.wait_for(...) are bounded by construction;
                # an adapter coroutine given timeout=... bounds its own HTTP call.
                if getattr(inner, "attr", "") in {"sleep", "wait_for"} and getattr(getattr(inner, "value", None), "id", "") == "asyncio":
                    continue
                if any(k.arg in {"timeout", "request_timeout"} for k in arg.keywords):
                    continue
            if path.startswith("data/connectors/"):
                continue  # each adapter sets an HTTP client timeout on every request (reviewed 1 Nov)
            hits.add((path, chains.get(node, "<module>"), node.lineno))
    return hits


def test_every_blocking_run_sync_call_has_a_time_limit():
    hits = _unbounded_calls()
    allowed = set(UNBOUNDED_BY_DESIGN) | OWNER_DECISION_PENDING
    chain_key = {(p, c) for p, c, _ in hits}
    unexpected = sorted(h for h in hits if (h[0], h[1]) not in allowed)
    assert not unexpected, "pass timeout= to run_sync (size it below the job interval):\n" + "\n".join(
        f"{p}:{line} in {c}" for p, c, line in unexpected)
    stale = sorted(allowed - chain_key)
    assert not stale, f"listed sites no longer unbounded; remove them from the lists: {stale}"
