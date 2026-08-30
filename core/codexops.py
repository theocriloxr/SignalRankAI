"""Read-only CodexOps governance primitives.

CodexOps produces audit findings and release evidence.  It has no code-write,
deployment, payment, broker, or secret-reading capability in this module.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class CodexOpsMode(StrEnum):
    READ_ONLY_AUDIT = "READ_ONLY_AUDIT"
    PATCH_PROPOSAL = "PATCH_PROPOSAL"
    LOCAL_PATCH = "LOCAL_PATCH"
    PR_MODE = "PR_MODE"
    RELEASE_GUARD = "RELEASE_GUARD"


@dataclass(frozen=True, slots=True)
class AuditFinding:
    code: str
    severity: str
    detail: str


_SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[^\s,;]+")


def mode() -> CodexOpsMode:
    raw = os.getenv("CODEXOPS_MODE", CodexOpsMode.READ_ONLY_AUDIT.value).strip().upper()
    try:
        return CodexOpsMode(raw)
    except ValueError:
        return CodexOpsMode.READ_ONLY_AUDIT


def audit_text(lines: Iterable[str]) -> tuple[AuditFinding, ...]:
    findings: list[AuditFinding] = []
    for line_no, line in enumerate(lines, 1):
        if _SECRET_PATTERN.search(str(line)):
            findings.append(AuditFinding("potential_secret", "high", f"line {line_no}: redaction required"))
    return tuple(findings)


__all__ = ["AuditFinding", "CodexOpsMode", "audit_text", "mode"]
