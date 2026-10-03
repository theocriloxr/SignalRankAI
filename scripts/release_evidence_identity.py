"""Bind certification to both the git commit and the bytes actually tested."""

from __future__ import annotations

import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import subprocess
import sys

SOURCE_ROOTS = {
    "admin", "alembic", "certification", "configs", "core", "data", "db", "delivery",
    "deploy", "engine", "execution", "frontend", "market", "migrations", "ml", "mobile",
    "observability", "payments", "paystack", "runtime", "scripts", "services",
    "signalrank_discord", "signalrank_telegram", "storage", "strategies", "tests",
    "tools", "utils", "web", "worker", ".github", "requirements",
}
GENERATED_PARTS = {"node_modules", "__pycache__", ".next", "dist", "dist-android", "dist-ios"}


def capture_release_identity(root: Path) -> dict[str, str | bool]:
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=root)

    sha = git("rev-parse", "HEAD").decode().strip()
    branch = git("branch", "--show-current").decode().strip()
    inventory = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
    digest = hashlib.sha256()
    for raw in sorted(set(inventory)):
        if not raw:
            continue
        name = raw.decode("utf-8")
        path = Path(name)
        if len(path.parts) > 1 and path.parts[0] not in SOURCE_ROOTS and path.parts[:2] != ("docs", "specs"):
            continue
        if GENERATED_PARTS.intersection(path.parts):
            continue
        # Ledger observations do not alter the executable candidate. The gate
        # manifest and certification code do, and remain in this digest.
        if name in {"certification/evidence_ledger.yaml", "certification/master_requirement_registry.json"}:
            continue
        absolute = root / path
        digest.update(raw + b"\0")
        digest.update(hashlib.sha256(absolute.read_bytes()).digest() if absolute.is_file() else b"DELETED")
    return {
        "git_sha": sha,
        "branch": branch,
        "source_sha256": digest.hexdigest(),
        "worktree_dirty": bool(git("status", "--porcelain").strip()),
    }


def validate_resume_identity(previous: dict, identity: dict, invocation: dict) -> None:
    if previous.get("release_identity") != identity or previous.get("invocation") != invocation:
        raise RuntimeError("certification_resume_source_or_configuration_mismatch: use a fresh output directory")


def verification_inputs(env: dict[str, str]) -> dict[str, str]:
    """Fingerprint actual verification configuration without exposing secrets."""
    packages = sorted((str(dist.metadata.get("Name", "")).lower(), dist.version) for dist in distributions())
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "environment_sha256": hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest(),
        "installed_packages_sha256": hashlib.sha256(json.dumps(packages).encode()).hexdigest(),
    }
