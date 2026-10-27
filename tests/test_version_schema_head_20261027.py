"""CX-OBS-03: /version must identify the schema it was built for.

Production reported ``schema_head: unknown`` because the value came only from a
manually maintained ``EXPECTED_SCHEMA_HEAD`` variable. The fallback is the code's
own single Alembic head, which the boot schema gate already enforces.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import web.app as web_app

ROOT = Path(__file__).resolve().parents[1]


def _repository_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "db" / "migrations"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    return str(heads[0])


def test_version_reports_code_schema_head_without_env(monkeypatch):
    monkeypatch.delenv("EXPECTED_SCHEMA_HEAD", raising=False)
    monkeypatch.setattr(web_app, "_code_schema_head_cache", None)
    payload = asyncio.run(web_app.version())
    assert payload.schema_head == _repository_head()
    assert payload.schema_head != "unknown"


def test_explicit_expected_schema_head_still_wins(monkeypatch):
    monkeypatch.setenv("EXPECTED_SCHEMA_HEAD", "0001_explicit")
    assert asyncio.run(web_app.version()).schema_head == "0001_explicit"


def test_schema_head_lookup_does_not_depend_on_working_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("EXPECTED_SCHEMA_HEAD", raising=False)
    monkeypatch.setattr(web_app, "_code_schema_head_cache", None)
    monkeypatch.chdir(tmp_path)
    assert web_app._code_schema_head() == _repository_head()


def test_build_timestamp_comes_from_the_nixpacks_build_stamp(monkeypatch, tmp_path):
    monkeypatch.delenv("BUILD_TIMESTAMP", raising=False)
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_CREATED_AT", raising=False)
    monkeypatch.setattr(web_app, "_REPOSITORY_ROOT", str(tmp_path))
    assert asyncio.run(web_app.version()).build_timestamp == "unknown"
    (tmp_path / ".build-timestamp").write_text("2026-10-27T22:30:00Z\n", encoding="utf-8")
    assert asyncio.run(web_app.version()).build_timestamp == "2026-10-27T22:30:00Z"


def test_malformed_build_stamp_is_reported_unknown_and_env_still_wins(monkeypatch, tmp_path):
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_CREATED_AT", raising=False)
    monkeypatch.setattr(web_app, "_REPOSITORY_ROOT", str(tmp_path))
    (tmp_path / ".build-timestamp").write_text("<script>not a date</script>", encoding="utf-8")
    monkeypatch.delenv("BUILD_TIMESTAMP", raising=False)
    assert asyncio.run(web_app.version()).build_timestamp == "unknown"
    monkeypatch.setenv("BUILD_TIMESTAMP", "2026-10-01T00:00:00Z")
    assert asyncio.run(web_app.version()).build_timestamp == "2026-10-01T00:00:00Z"


def test_nixpacks_build_phase_writes_the_stamp_without_failing_builds():
    import tomllib

    config = tomllib.loads((ROOT / "nixpacks.toml").read_text(encoding="utf-8"))
    commands = config["phases"]["build"]["cmds"]
    assert any(".build-timestamp" in command and command.rstrip().endswith("|| true") for command in commands)
    assert not any("alembic" in command for command in commands)
    assert ".build-timestamp" in (ROOT / ".gitignore").read_text(encoding="utf-8")
