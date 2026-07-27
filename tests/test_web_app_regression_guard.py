"""Regression guards for the canonical ASGI web application.

The production web surface was once accidentally replaced by a legacy Flask
file.  These tests intentionally verify semantics instead of merely importing
``web.app``.
"""
from __future__ import annotations

from fastapi import FastAPI


def test_web_app_is_fastapi_and_exposes_security_routes() -> None:
    from web.app import app

    assert isinstance(app, FastAPI)
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/broker/validate-api-permissions" in paths
    assert "/broker/exchange/link" in paths
    assert "/api/v1/signals" in paths


def test_web_app_exports_auth_dependency_for_broker_routes() -> None:
    from web.app import verify_api_key

    assert callable(verify_api_key)
