#!/usr/bin/env python3
"""Run pytest and terminate deterministically after pytest returns.

Some optional integration dependencies start non-daemon resources during test
collection. On constrained CI/container runtimes those resources can keep the
interpreter alive after pytest has already printed its final summary. This
wrapper preserves pytest's real exit status and output, then uses ``os._exit``
only after ``pytest.main`` has returned, preventing post-test resource leaks
from hanging the complete certification orchestrator.

This file is test tooling only and is never imported by the production runtime.
"""
from __future__ import annotations

import os
import sys

import pytest


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    code = int(pytest.main(args))
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(code)  # noqa: PLW1510 - deterministic test-process teardown


if __name__ == "__main__":
    main()
