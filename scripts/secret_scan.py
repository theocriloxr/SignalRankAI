#!/usr/bin/env python3
"""Fail-closed source secret scan for deployable files.

The scan ignores generated environments, VCS metadata and documentation while
checking production source/config files for token-shaped literals and private
keys. Environment variable names and obvious test placeholders are allowed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules", ".pytest-tmp"}
ALLOWED_SUFFIXES = {".py", ".toml", ".json", ".yml", ".yaml", ".sh", ".ini", ".sql", ".example"}
PLACEHOLDERS = {"test", "example", "placeholder", "changeme", "do_not_use", "invalid", "your_", "xxxx"}
PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("telegram_token", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    ("github_token", re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("paystack_secret", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("generic_api_key", re.compile(r"(?i)(?:api[_-]?key|secret|token)\s*[:=]\s*['\"]([A-Za-z0-9_\-]{32,})['\"]")),
]


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        if path.suffix.lower() in ALLOWED_SUFFIXES or path.name in {"Dockerfile", "Procfile", "start.sh"}:
            yield path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    findings: list[str] = []
    root = Path(args.root).resolve()
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for label, pattern in PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(1) if match.lastindex else match.group(0)
                lowered = value.lower()
                if any(marker in lowered for marker in PLACEHOLDERS):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(root)}:{line}:{label}")
    if findings:
        print("[secret_scan] FAILED")
        for finding in findings[:100]:
            print(finding)
        return 1
    print("[secret_scan] PASS findings=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
