"""The client's IP address, taken only from sources a client cannot forge (29 Oct 2026).

Rate limits, security events and the Paystack IP allowlist used the first
``X-Forwarded-For`` value, which is whatever the client sends. Order of trust:

1. A client IP signed by our own web proxy (``x-signalrank-client-ip`` with an
   HMAC over ip and timestamp, keyed by ``SIGNALRANK_CLIENT_IP_SECRET``). This
   survives a second pass through the public edge, where the edge would
   otherwise replace the address with the proxy's own.
2. ``TRUSTED_CLIENT_IP_HEADER``; on Railway it defaults to ``x-real-ip``, which
   Railway's edge sets to the client's remote address (Railway public
   networking specs). If set to ``x-forwarded-for``, the right-most entry
   (added by the nearest proxy) is used, never the client-supplied first one.
3. The socket peer.

Values that are not IP addresses are ignored at every step.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import time
from typing import Any

SIGNED_IP_HEADER = "x-signalrank-client-ip"
SIGNED_TS_HEADER = "x-signalrank-client-ip-ts"
SIGNED_SIG_HEADER = "x-signalrank-client-ip-signature"
SIGNATURE_MAX_AGE_SECONDS = 300
_RAILWAY_MARKERS = ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID")


def _valid_ip(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def trusted_header() -> str:
    configured = os.getenv("TRUSTED_CLIENT_IP_HEADER")
    if configured is not None:
        return configured.strip().lower()
    on_railway = any(str(os.getenv(name) or "").strip() for name in _RAILWAY_MARKERS)
    return "x-real-ip" if on_railway else ""


def client_ip_signature(secret: str, ip: str, timestamp: str) -> str:
    return hmac.new(secret.encode("utf-8"), f"{ip}.{timestamp}".encode("utf-8"), hashlib.sha256).hexdigest()


def _signed_ip(headers: Any, now: float | None = None) -> str | None:
    secret = str(os.getenv("SIGNALRANK_CLIENT_IP_SECRET") or "")
    if len(secret) < 32:
        return None
    ip = _valid_ip(headers.get(SIGNED_IP_HEADER))
    timestamp = str(headers.get(SIGNED_TS_HEADER) or "")
    signature = str(headers.get(SIGNED_SIG_HEADER) or "")
    if not ip or not timestamp.isdigit() or not signature:
        return None
    if abs((time.time() if now is None else now) - int(timestamp)) > SIGNATURE_MAX_AGE_SECONDS:
        return None
    expected = client_ip_signature(secret, str(headers.get(SIGNED_IP_HEADER)).strip(), timestamp)
    return ip if hmac.compare_digest(expected, signature) else None


def resolve_client_ip(request: Any, *, now: float | None = None) -> tuple[str | None, str]:
    """Return ``(ip, source)`` where source names the trusted origin of the address."""
    headers = getattr(request, "headers", None) or {}
    signed = _signed_ip(headers, now=now)
    if signed:
        return signed, "signed_proxy"
    header = trusted_header()
    if header:
        raw = str(headers.get(header) or "")
        if header == "x-forwarded-for":
            raw = raw.split(",")[-1]
        ip = _valid_ip(raw)
        if ip:
            return ip, header
    client = getattr(request, "client", None)
    return _valid_ip(getattr(client, "host", None)), "socket"


def client_ip(request: Any) -> str | None:
    return resolve_client_ip(request)[0]


__all__ = [
    "SIGNED_IP_HEADER", "SIGNED_SIG_HEADER", "SIGNED_TS_HEADER", "client_ip", "client_ip_signature",
    "resolve_client_ip", "trusted_header",
]
