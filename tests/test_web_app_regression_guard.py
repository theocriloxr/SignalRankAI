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
    # FastAPI 0.135+ may retain included routers lazily as `_IncludedRouter`
    # objects without a direct `path`. OpenAPI is the stable public view of
    # the fully expanded HTTP surface across supported FastAPI releases.
    paths = set(app.openapi()["paths"])
    assert "/broker/validate-api-permissions" in paths
    assert "/broker/exchange/link" in paths
    assert "/api/v1/signals" in paths


def test_web_app_exports_auth_dependency_for_broker_routes() -> None:
    from web.app import verify_api_key

    assert callable(verify_api_key)
