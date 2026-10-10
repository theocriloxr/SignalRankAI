from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import pytest

from scripts import generate_release_provenance as provenance


COMMIT = "a" * 40
BRANCH = "test/release-provenance"


@pytest.mark.parametrize("entrypoint", ["verifier", "isolated_metadata"])
def test_migration_inspection_and_release_cli_do_not_require_pythonpath(entrypoint):
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE",
        "APPDATA", "LOCALAPPDATA", "COMSPEC", "PROGRAMFILES", "PROGRAMFILES(X86)",
        "PROGRAMDATA", "HOMEDRIVE", "HOMEPATH"}}
    env.update(APP_ENV="test", ENVIRONMENT="test", SIGNALRANK_ALLOW_DOTENV="0",
        SIGNALRANK_DISABLE_BACKGROUND_THREADS="1", GLOBAL_EXECUTION_KILL_SWITCH="1",
        REAL_EXECUTION_ENABLED="0", AUTO_EXECUTION_ENABLED="0", AUTO_TRADE_ENABLED="0",
        COPY_TRADE_ENABLED="0", PROP_EXECUTION_ENABLED="0", REAL_PAYOUTS_ENABLED="0",
        DATABASE_URL="postgresql+asyncpg://unused@127.0.0.1:1/signalrank_release_test")
    if entrypoint == "verifier":
        command = [sys.executable, str(root / "scripts/verify_release_chain.py")]
        marker = "ALEMBIC_RELEASE_CHAIN_PASS head=0051_strategy_health_baselines"
    else:
        command = [sys.executable, "-I", "-c",
            "from alembic.config import Config; from alembic.script import ScriptDirectory; "
            "print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"]
        marker = "['0051_strategy_health_baselines']"
    result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert marker in result.stdout


def test_locked_components_are_unique_and_pinned():
    components = provenance.locked_components()
    assert len(components) >= 50
    keys = [item["name"].lower().replace("_", "-") for item in components]
    assert len(keys) == len(set(keys))
    assert all(item["version"] for item in components)
    assert all(item["purl"].startswith("pkg:pypi/") for item in components)


def test_release_identity_requires_exact_sha():
    commit, branch = provenance.release_identity(COMMIT, BRANCH)
    assert commit == COMMIT
    assert branch == BRANCH
    with pytest.raises(ValueError, match="40_char_sha"):
        provenance.release_identity("abc", BRANCH)


def test_platform_markers_are_preserved_without_polluting_versions():
    components = {item["name"]: item for item in provenance.locked_components()}
    uvloop = components["uvloop"]
    assert uvloop["version"] == "0.22.1"
    assert uvloop["purl"] == "pkg:pypi/uvloop@0.22.1"
    assert uvloop["properties"] == [{"name": "signalrank:environment-marker", "value": 'sys_platform != "win32"'}]


def test_sbom_and_provenance_are_deterministic(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_digests = provenance.write_bundle(first, commit=COMMIT, branch=BRANCH)
    second_digests = provenance.write_bundle(second, commit=COMMIT, branch=BRANCH)

    assert first_digests == second_digests
    for name in ("sbom.cdx.json", "release-provenance.json", "SHA256SUMS"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_provenance_binds_current_release_lock_and_dockerfile(tmp_path: Path):
    provenance.write_bundle(tmp_path, commit=COMMIT, branch=BRANCH)
    report = json.loads((tmp_path / "release-provenance.json").read_text())
    sbom = json.loads((tmp_path / "sbom.cdx.json").read_text())

    assert report["release"]["git_commit"] == COMMIT
    assert report["release"]["git_branch"] == BRANCH
    assert report["release"]["alembic_head"] == "0051_strategy_health_baselines"
    assert report["inputs"]["requirements.lock"]["sha256"] == provenance.sha256_file(
        provenance.LOCK
    )
    assert report["inputs"]["Dockerfile"]["sha256"] == provenance.sha256_file(
        provenance.DOCKERFILE
    )
    assert report["policy"]["dependency_resolution"] == "locked-no-deps-plus-pip-check"
    assert report["policy"]["artifact_signing"] == "external-key-required"
    assert report["policy"]["live_money_activation_implied"] is False
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"


def test_self_verification_detects_tampering(tmp_path: Path):
    provenance.write_bundle(tmp_path, commit=COMMIT, branch=BRANCH)
    provenance.verify_bundle(tmp_path, commit=COMMIT, branch=BRANCH)

    (tmp_path / "sbom.cdx.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="release_provenance_mismatch:sbom.cdx.json"):
        provenance.verify_bundle(tmp_path, commit=COMMIT, branch=BRANCH)


def test_docker_image_governance_does_not_require_git_metadata():
    dockerfile = provenance.DOCKERFILE.read_text(encoding="utf-8")
    builder, runtime = dockerfile.split(" AS runtime", 1)
    governance = (provenance.ROOT / "scripts" / "build_v7_governance.py").read_text(encoding="utf-8")
    install_lines = re.findall(
        r"apt-get install -y --no-install-recommends\s+([^&;\n]+)",
        builder.replace("\\\n", " "),
    )
    packages = {word.split("=", 1)[0] for line in install_lines for word in shlex.split(line)}
    assert {"gcc", "libpq-dev"} <= packages
    assert "git" not in packages
    assert " git " not in runtime.replace("\n", " ")
    assert "python scripts/run_release_manifest.py --environment image --group image" in builder
    assert "def _packaged_legacy_disposition()" in governance
    assert "except (FileNotFoundError, subprocess.CalledProcessError)" in governance
    assert "packaged_governance_missing_legacy_disposition" in governance
