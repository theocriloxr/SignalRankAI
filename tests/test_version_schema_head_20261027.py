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
