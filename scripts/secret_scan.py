#!/usr/bin/env python3
"""Fail-closed source secret scan for deployable files.

The scan checks release source, configuration and documentation for token-shaped
literals and private keys. Ignored local artifacts are outside the release scope;
tracked files remain in scope even inside ignored directories. Environment
variable references and explicit test placeholders are allowed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "venv", ".audit-venv", ".audit-tools-venv", "__pycache__", ".pytest_cache", "node_modules", ".pytest-tmp"}
ALLOWED_SUFFIXES = {
    ".py",
    ".toml",
    ".json",
    ".yml",
    ".yaml",
    ".sh",
    ".ini",
    ".sql",
    ".example",
    ".md",
    ".txt",
    ".env",
}
PLACEHOLDERS = {
    "test",
    "example",
    "placeholder",
    "changeme",
    "do_not_use",
    "invalid",
    "your_",
    "xxxx",
    "redacted",
    "generate_",
    "rotate_required",
}
PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("telegram_token", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    ("github_token", re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("paystack_secret", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("generic_api_key", re.compile(r"(?i)(?:api[_-]?key|secret|token)\s*[:=]\s*['\"]([A-Za-z0-9_\-]{32,})['\"]")),
    (
        "sensitive_assignment",
        re.compile(
            r"(?im)\b(?:[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY)|"
            r"ADMIN_API_TOKEN|ENCRYPTION_KEY|FERNET_KEY|BYPASS_KEY)"
            r"[ \t]*[:=][ \t]*(?:['\"]([^'\"\r\n]{8,})['\"]|"
            r"([A-Za-z0-9_./:+-]{16,}))"
        ),
    ),
]


def iter_files(root: Path):
    import os

    # Release scans cover tracked and non-ignored candidate source, including
    # tracked files beneath otherwise ignored directories. Local audit downloads
    # and generated test keys are not inputs to a committed release.
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, check=True,
        )
        for name in sorted(set(result.stdout.decode("utf-8").split("\0")) - {""}):
            path = root / name
            if path.is_file() and (path.suffix.lower() in ALLOWED_SUFFIXES or path.name in {"Dockerfile", "Procfile", "start.sh"}):
                yield path
        return
    for directory, subdirs, names in os.walk(root):
        subdirs[:] = [name for name in subdirs if name not in EXCLUDED_PARTS]
        for name in names:
            path = Path(directory) / name
            if path.suffix.lower() in ALLOWED_SUFFIXES or name in {"Dockerfile", "Procfile", "start.sh"}:
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
            if label == "sensitive_assignment" and path.suffix.lower() not in {
                ".md",
                ".txt",
                ".env",
                ".example",
            }:
                continue
            for match in pattern.finditer(text):
                if match.lastindex:
                    value = next(
                        (group for group in match.groups() if group is not None),
                        match.group(0),
                    )
                else:
                    value = match.group(0)
                lowered = value.lower()
                # "test" in sk_test_ identifies a real provider credential mode,
                # not a dummy value. Never waive a token for an internal substring.
                placeholder_value = lowered
                if label == "paystack_secret":
                    placeholder_value = lowered.split("_", 2)[-1]
                elif re.fullmatch(r"\d{5,12}:[A-Za-z0-9_-]+", value):
                    placeholder_value = lowered.split(":", 1)[-1]
                obvious_placeholder = any(
                    placeholder_value == marker or placeholder_value.startswith(marker + "_")
                    or placeholder_value.startswith(marker + "-")
                    or (marker.endswith("_") and placeholder_value.startswith(marker))
                    for marker in PLACEHOLDERS
                )
                if (
                    value.startswith("${{")
                    or value.startswith("<")
                    or obvious_placeholder
                    # Only an unquoted symbolic environment/config reference is
                    # exempt. Token-shaped quoted literals and provider tokens
                    # must not be allowed just because they are valid identifiers.
                    or (label == "sensitive_assignment" and match.group(2) is not None
                        and re.fullmatch(r"[A-Z_][A-Z0-9_]*", value) is not None)
                    or value.startswith(("config.", "os.getenv", "settings."))
                ):
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
