"""Generate and verify deterministic SignalRankAI release provenance.

The generated bundle contains:
- CycloneDX 1.5 SBOM from the certified requirements.lock graph.
- release-provenance.json binding dependency/file hashes to the exact release.
- SHA-256 digest file for both artifacts.

No signing key is created or guessed here. External artifact signing/attestation
can sign the deterministic digest produced by this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock"
DOCKERFILE = ROOT / "Dockerfile"
CURRENT_RELEASE = ROOT / "CURRENT_RELEASE.md"
ALEMBIC_RE = re.compile(r"Repository Alembic head:\s*([A-Za-z0-9_\-]+)")
REQ_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==([^\s#]+)$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def git_value(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def release_identity(commit: str | None = None, branch: str | None = None) -> tuple[str, str]:
    resolved_commit = str(
        commit
        or os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT_SHA")
        or git_value("rev-parse", "HEAD")
        or ""
    ).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", resolved_commit):
        raise ValueError("release_commit_must_be_exact_40_char_sha")

    resolved_branch = str(
        branch
        or os.getenv("RAILWAY_GIT_BRANCH")
        or os.getenv("GIT_BRANCH")
        or git_value("rev-parse", "--abbrev-ref", "HEAD")
        or "unknown"
    ).strip()
    if not resolved_branch:
        raise ValueError("release_branch_required")
    return resolved_commit, resolved_branch


def alembic_head() -> str:
    text = CURRENT_RELEASE.read_text(encoding="utf-8")
    match = ALEMBIC_RE.search(text)
    if not match:
        raise ValueError("current_release_alembic_head_missing")
    return match.group(1)


def locked_components() -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in LOCK.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = REQ_RE.match(line)
        if not match:
            raise ValueError(f"unsupported_lock_line:{line[:120]}")
        name, version = match.groups()
        key = name.lower().replace("_", "-")
        if key in seen:
            raise ValueError(f"duplicate_locked_component:{key}")
        seen.add(key)
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{key}@{version}",
            }
        )
    return sorted(components, key=lambda item: (item["name"].lower(), item["version"]))


def build_bundle(commit: str, branch: str) -> tuple[dict[str, Any], dict[str, Any]]:
    components = locked_components()
    lock_hash = sha256_file(LOCK)
    docker_hash = sha256_file(DOCKERFILE)
    current_release_hash = sha256_file(CURRENT_RELEASE)
    head = alembic_head()

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "SignalRankAI",
                "version": commit[:12],
                "properties": [
                    {"name": "signalrank:git_commit", "value": commit},
                    {"name": "signalrank:git_branch", "value": branch},
                    {"name": "signalrank:alembic_head", "value": head},
                    {"name": "signalrank:requirements_lock_sha256", "value": lock_hash},
                ],
            }
        },
        "components": components,
    }
    sbom_hash = sha256_bytes(canonical_json(sbom))
    provenance = {
        "schema_version": 1,
        "project": "SignalRankAI",
        "release": {
            "git_commit": commit,
            "git_branch": branch,
            "alembic_head": head,
        },
        "inputs": {
            "requirements.lock": {"sha256": lock_hash, "component_count": len(components)},
            "Dockerfile": {"sha256": docker_hash},
            "CURRENT_RELEASE.md": {"sha256": current_release_hash},
        },
        "artifacts": {
            "sbom.cdx.json": {"sha256": sbom_hash, "format": "CycloneDX-1.5"},
        },
        "policy": {
            "dependency_resolution": "locked-no-deps-plus-pip-check",
            "artifact_signing": "external-key-required",
            "live_money_activation_implied": False,
        },
    }
    return sbom, provenance


def write_bundle(output_dir: Path, *, commit: str, branch: str) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sbom, provenance = build_bundle(commit, branch)
    sbom_bytes = canonical_json(sbom)
    provenance_bytes = canonical_json(provenance)

    sbom_path = output_dir / "sbom.cdx.json"
    provenance_path = output_dir / "release-provenance.json"
    digest_path = output_dir / "SHA256SUMS"
    sbom_path.write_bytes(sbom_bytes)
    provenance_path.write_bytes(provenance_bytes)

    digests = {
        sbom_path.name: sha256_bytes(sbom_bytes),
        provenance_path.name: sha256_bytes(provenance_bytes),
    }
    digest_path.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(digests.items())),
        encoding="utf-8",
    )
    return digests


def verify_bundle(output_dir: Path, *, commit: str, branch: str) -> None:
    expected_dir = output_dir / ".expected"
    if expected_dir.exists():
        for item in expected_dir.iterdir():
            item.unlink()
        expected_dir.rmdir()
    expected = write_bundle(expected_dir, commit=commit, branch=branch)
    for name in ("sbom.cdx.json", "release-provenance.json", "SHA256SUMS"):
        actual = output_dir / name
        wanted = expected_dir / name
        if not actual.exists():
            raise RuntimeError(f"release_provenance_missing:{name}")
        if actual.read_bytes() != wanted.read_bytes():
            raise RuntimeError(f"release_provenance_mismatch:{name}")
    for item in expected_dir.iterdir():
        item.unlink()
    expected_dir.rmdir()
    print(
        "RELEASE_PROVENANCE_PASS "
        + json.dumps(
            {
                "commit": commit,
                "branch": branch,
                "alembic_head": alembic_head(),
                "components": len(locked_components()),
                "sbom_sha256": expected["sbom.cdx.json"],
            },
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="/tmp/signalrank-release-provenance")
    parser.add_argument("--commit")
    parser.add_argument("--branch")
    parser.add_argument("--verify-self", action="store_true")
    args = parser.parse_args()

    commit, branch = release_identity(args.commit, args.branch)
    output_dir = Path(args.output_dir)
    digests = write_bundle(output_dir, commit=commit, branch=branch)
    if args.verify_self:
        verify_bundle(output_dir, commit=commit, branch=branch)
    else:
        print(
            "RELEASE_PROVENANCE_GENERATED "
            + json.dumps(
                {
                    "output_dir": str(output_dir),
                    "commit": commit,
                    "branch": branch,
                    "digests": digests,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
