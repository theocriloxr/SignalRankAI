"""The public address users open from Telegram links (8 Nov 2026).

Bot links (/app sign-in, broker linking, the legacy dashboard) took
``RAILWAY_PUBLIC_DOMAIN`` before ``APP_BASE_URL``. Production left Railway on
29 Oct 2026; a leftover Railway variable would send users to a dead address.
The configured app address now wins, as in ``web.platform_api._app_base_url_from_env``;
on staging the staging address is used so production links never leak there.
"""
from __future__ import annotations

import os


def public_app_base_url() -> str:
    try:
        from core.env import runtime_environment_name

        staging = runtime_environment_name("dev") == "staging"
    except Exception:
        staging = False
    if staging:
        order = ("STAGING_APP_BASE_URL", "RAILWAY_PUBLIC_DOMAIN", "WEBHOOK_BASE_URL")
    else:
        order = ("APP_BASE_URL", "RAILWAY_PUBLIC_DOMAIN", "STAGING_APP_BASE_URL", "WEBHOOK_BASE_URL")
    value = next((str(os.getenv(name) or "").strip() for name in order if str(os.getenv(name) or "").strip()), "")
    value = value.rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value
