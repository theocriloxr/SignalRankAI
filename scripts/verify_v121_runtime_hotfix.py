#!/usr/bin/env python3
"""Offline verifier for the v1.2.1 Railway runtime hotfix."""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def main() -> int:
    from db.session import get_session
    from engine.adaptive.elliott import ElliottWaveComponent as legacy
    from engine.adaptive.components.elliott import ElliottWaveComponent as canonical

    if legacy is not canonical:
        _fail("legacy Elliott import does not resolve to the canonical component")

    signature = inspect.signature(get_session)
    for name in ("timeout_seconds", "timeout"):
        if name not in signature.parameters:
            _fail(f"get_session is missing {name}")

    stale: list[str] = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", "__pycache__", "tests"} for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else ""
            if name == "get_session" and any(keyword.arg == "timeout" for keyword in node.keywords):
                stale.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    if stale:
        _fail("stale get_session(timeout=...) callsites: " + ", ".join(stale))

    profile = (ROOT / "SignalRankAI_v1.2.1_Railway_Staging_Safe.env.example").read_text(encoding="utf-8")
    required_off = (
        "REAL_EXECUTION_ENABLED=0",
        "AUTO_EXECUTION_ENABLED=0",
        "AUTO_TRADE_ENABLED=0",
        "COPY_TRADE_ENABLED=0",
        "REAL_PAYOUTS_ENABLED=0",
        "PAYMENTS_PUBLIC_ENABLED=1",
        "FREE_SIGNAL_DISTRIBUTION_ENABLED=0",
        "WS_INGEST_ENABLED=0",
        "PROXY_VALIDATION_ENABLED=0",
    )
    missing = [line for line in required_off if line not in profile]
    if missing:
        _fail("staging profile missing safe values: " + ", ".join(missing))

    print("PASS v1.2.1 runtime hotfix verification")
    print("legacy_elliott_import=PASS")
    print("db_timeout_contract=PASS")
    print("stale_timeout_calls=0")
    print("staging_safety_profile=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
