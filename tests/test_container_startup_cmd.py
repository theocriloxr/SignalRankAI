"""Regression test: deployment start commands must not lead with VAR=value tokens.

When Railway (or any OCI runtime) executes a startCommand in exec form — without
wrapping it in `sh -c` — the first whitespace-separated token is treated as the
executable name.  A prefix like ``MALLOC_ARENA_MAX=2 python ...`` therefore
produces:

    The executable 'MALLOC_ARENA_MAX=2' could not be found.

This test ensures that neither ``railway.json``'s ``startCommand`` nor
``nixpacks.toml``'s ``[start] cmd`` begins with a shell variable-assignment token
(``IDENTIFIER=value``).  Environment variables must instead be declared in
``nixpacks.toml [variables]`` or set via Railway's environment panel.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Pattern that matches a leading VAR=value shell assignment token.
# Matches things like: MALLOC_ARENA_MAX=2, FOO=bar, SOME_VAR=any_value
_LEADING_ASSIGNMENT_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*=[^\s]")

REPO_ROOT = Path(__file__).resolve().parents[1]


def _has_leading_assignment(cmd: str) -> bool:
    """Return True if *cmd* starts with a shell variable-assignment token."""
    return bool(_LEADING_ASSIGNMENT_RE.match(cmd))


def test_railway_json_startCommand_not_leading_assignment() -> None:
    """railway.json startCommand must not start with VAR=value."""
    railway_json = REPO_ROOT / "railway.json"
    assert railway_json.exists(), "railway.json not found in repo root"

    data = json.loads(railway_json.read_text(encoding="utf-8"))
    start_cmd: str | None = data.get("deploy", {}).get("startCommand")
    assert start_cmd is not None, "railway.json missing deploy.startCommand"

    assert not _has_leading_assignment(start_cmd), (
        f"railway.json startCommand begins with a VAR=value assignment which will "
        f"be interpreted as the executable name in exec-form container runtimes.\n"
        f"  startCommand: {start_cmd!r}\n"
        f"Move env vars to Railway's environment settings or nixpacks.toml [variables]."
    )


def test_nixpacks_toml_start_cmd_not_leading_assignment() -> None:
    """nixpacks.toml [start] cmd must not start with VAR=value."""
    nixpacks_toml = REPO_ROOT / "nixpacks.toml"
    assert nixpacks_toml.exists(), "nixpacks.toml not found in repo root"

    # Parse just the cmd line without a full TOML parser dependency.
    # Look for: cmd = "..." under a [start] section.
    content = nixpacks_toml.read_text(encoding="utf-8")
    in_start_section = False
    cmd_value: str | None = None
    cmd_re = re.compile(r'^\s*cmd\s*=\s*"(.+)"\s*$')
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[start]":
            in_start_section = True
            continue
        if in_start_section and stripped.startswith("[") and stripped != "[start]":
            # Entered a new section — stop searching.
            in_start_section = False
            continue
        if in_start_section:
            m = cmd_re.match(line)
            if m:
                cmd_value = m.group(1)
                break

    assert cmd_value is not None, (
        "nixpacks.toml [start] section missing cmd = \"...\" line"
    )

    assert not _has_leading_assignment(cmd_value), (
        f"nixpacks.toml [start] cmd begins with a VAR=value assignment which will "
        f"be interpreted as the executable name in exec-form container runtimes.\n"
        f"  cmd: {cmd_value!r}\n"
        f"Move env vars to nixpacks.toml [variables] instead."
    )
