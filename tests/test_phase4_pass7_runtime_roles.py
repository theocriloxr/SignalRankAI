"""Focused contract tests for the Pass 7 role boundary."""

from __future__ import annotations

import importlib

import pytest

from runtime.dispatcher import dispatch
from runtime.roles import RunMode, infer_run_mode, parse_run_mode, role_spec


def test_parse_run_mode_accepts_canonical_roles_and_legacy_aliases() -> None:
    assert parse_run_mode("all/dev") is RunMode.ALL_DEV
    assert parse_run_mode("all") is RunMode.ALL_DEV
    assert parse_run_mode("worker") is RunMode.DELIVERY
    assert parse_run_mode("scheduler") is RunMode.SCHEDULER


def test_parse_run_mode_rejects_unknown_role() -> None:
    with pytest.raises(ValueError, match="Unknown RUN_MODE"):
        parse_run_mode("not-a-role")


def test_infer_run_mode_preserves_engine_default_and_service_mapping() -> None:
    assert infer_run_mode({}) is RunMode.ENGINE
    assert infer_run_mode({"RAILWAY_SERVICE_NAME": "signalrankai-outcome"}) is RunMode.OUTCOME
    assert infer_run_mode({"RAILWAY_SERVICE_NAME": "signalrankai-telegram"}) is RunMode.BOT


def test_role_specs_are_explicit() -> None:
    assert role_spec(RunMode.DELIVERY).owns.startswith("Delivery")
    assert role_spec("worker").mode is RunMode.DELIVERY


def test_role_modules_import_without_starting_work() -> None:
    modules = (
        "runtime.roles",
        "runtime.dispatcher",
        "runtime.web",
        "runtime.bot",
        "runtime.engine",
        "runtime.delivery",
        "runtime.outcome",
        "runtime.analytics",
        "runtime.scheduler",
        "runtime.all_dev",
    )
    for module_name in modules:
        assert importlib.import_module(module_name)


def test_dispatch_uses_lazy_role_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = importlib.import_module("runtime.analytics")
    called: list[bool] = []
    monkeypatch.setattr(adapter, "run", lambda: called.append(True))
    dispatch("analytics")
    assert called == [True]
