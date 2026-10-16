"""Authenticate once over verified TLS; never send an email or print credentials."""
from __future__ import annotations

import json
import os
import smtplib
import ssl
from typing import Mapping


def authenticate(env: Mapping[str, str] | None = None) -> dict[str, object]:
    settings = os.environ if env is None else env
    host = str(settings.get("SMTP_HOST", "")).strip()
    username = str(settings.get("SMTP_USERNAME", "")).strip()
    password = str(settings.get("SMTP_PASSWORD", ""))
    if not host or not username or not password:
        raise ValueError("smtp_host_username_password_required")
    port = int(settings.get("SMTP_PORT", "587"))
    timeout = float(settings.get("SMTP_TIMEOUT_SECONDS", "15"))
    if not 1 <= port <= 65535 or not 0 < timeout <= 60:
        raise ValueError("smtp_invalid_port_or_timeout")
    enabled = {"1", "true", "yes", "on"}
    use_ssl = str(settings.get("SMTP_USE_SSL", "0")).lower() in enabled
    starttls = str(settings.get("SMTP_USE_STARTTLS", "1")).lower() in enabled
    if not use_ssl and not starttls:
        raise ValueError("smtp_verified_tls_required")
    context = ssl.create_default_context()
    client = (smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
              if use_ssl else smtplib.SMTP(host, port, timeout=timeout))
    with client:
        client.ehlo()
        if not use_ssl:
            client.starttls(context=context)
            client.ehlo()
        client.login(username, password)
    return {"status": "PASS", "authenticated": True, "tls_verified": True,
            "email_sent": False, "scope": "SMTP_AUTHENTICATION_ONLY"}


def main() -> int:
    try:
        result = authenticate()
    except smtplib.SMTPAuthenticationError as exc:
        result = {"status": "FAILED", "reason": "smtp_authentication_rejected",
                  "smtp_code": exc.smtp_code, "email_sent": False,
                  "required_action": "Verify or replace provider SMTP credentials in Railway; do not paste them into chat."}
    except ValueError as exc:
        reason = str(exc)
        if reason not in {"smtp_host_username_password_required", "smtp_invalid_port_or_timeout", "smtp_verified_tls_required"}:
            reason = "smtp_invalid_configuration"
        result = {"status": "FAILED", "reason": reason, "email_sent": False}
    except Exception as exc:
        result = {"status": "FAILED", "reason": type(exc).__name__, "email_sent": False}
    print("SMTP_PREFLIGHT " + json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
