#!/usr/bin/env python3
"""Fail when production code still uses legacy DB session boolean flags."""
from __future__ import annotations

import ast
from pathlib import Path

ROOTS = ("db", "engine", "worker", "signalrank_telegram", "services", "core", "data", "payments", "web")
LEGACY = {"noncritical", "critical", "interactive"}


def audit(root: Path = Path('.')) -> list[str]:
    findings: list[str] = []
    for folder in ROOTS:
        base = root / folder
        if not base.exists():
            continue
        for path in base.rglob('*.py'):
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except Exception as exc:
                findings.append(f"{path}:parse_error:{type(exc).__name__}:{exc}")
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
                if name not in {"get_session", "_profile_get_session"}:
                    continue
                used = [kw.arg for kw in node.keywords if kw.arg in LEGACY]
                if used:
                    findings.append(f"{path}:{node.lineno}:legacy_flags={','.join(sorted(used))}")
    return findings


if __name__ == '__main__':
    problems = audit()
    if problems:
        print('[db_session_api] legacy_call_sites=%s' % len(problems))
        print('\n'.join(problems))
        raise SystemExit(1)
    print('[db_session_api] legacy_call_sites=0')
