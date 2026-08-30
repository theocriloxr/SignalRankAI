"""Compatibility redirect for the retired insecure numeric-ID dashboard.

The previous implementation accepted an arbitrary integer user ID as a login.
That is an IDOR/account-takeover vulnerability and is intentionally removed.
All users must authenticate through the unified FastAPI platform application.
"""
from __future__ import annotations

import os
from flask import Flask, abort, redirect

app = Flask(__name__)


def _platform_url() -> str:
    base = str(
        os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("APP_BASE_URL")
        or os.getenv("STAGING_APP_BASE_URL")
        or os.getenv("WEBHOOK_BASE_URL")
        or "/app"
    ).rstrip("/")
    if base != "/app" and not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base if base.endswith("/app") else f"{base}/app"


@app.route("/")
@app.route("/login", methods=["GET", "POST"])
@app.route("/dashboard")
def retired_dashboard():
    if str(os.getenv("LEGACY_USERDASH_ENABLED", "0")).lower() in {"1", "true", "yes", "on"}:
        # Even when the compatibility process is left running, it never accepts
        # legacy user-id credentials; it only redirects to secure authentication.
        return redirect(_platform_url(), code=302)
    return redirect(_platform_url(), code=302)


@app.route("/logout")
def logout():
    return redirect(_platform_url(), code=302)


if __name__ == "__main__":
    app.run(debug=False, port=int(os.getenv("PORT", "5000")))
