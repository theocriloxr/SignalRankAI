#!/usr/bin/env python3
"""Inspect and safely repair the SignalRankAI Telegram webhook.

The bot token is read from TELEGRAM_BOT_TOKEN. The script never prints it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib import error, parse, request

DEFAULT_ALLOWED = [
    "message",
    "edited_message",
    "callback_query",
    "my_chat_member",
    "chat_member",
    "pre_checkout_query",
    "shipping_query",
]


def _api(token: str, method: str, data: dict[str, object] | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    encoded = None
    headers = {"User-Agent": "SignalRankAI-webhook-recovery/1"}
    if data is not None:
        encoded = parse.urlencode(
            {
                key: json.dumps(value, separators=(",", ":"))
                if isinstance(value, (list, dict))
                else str(value).lower()
                if isinstance(value, bool)
                else str(value)
                for key, value in data.items()
            }
        ).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with request.urlopen(request.Request(url, data=encoded, headers=headers), timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except Exception:
            detail = {"description": body[:500]}
        raise RuntimeError(
            f"Telegram {method} failed: HTTP {exc.code}: {detail.get('description', 'unknown error')}"
        ) from None
    except Exception as exc:
        raise RuntimeError(f"Telegram {method} failed: {type(exc).__name__}: {exc}") from None
    if not payload.get("ok"):
        raise RuntimeError(
            f"Telegram {method} failed: {payload.get('description', 'unknown error')}"
        )
    return payload


def _base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if value and not value.startswith("https://"):
        value = "https://" + value
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", action="store_true", help="register the expected webhook safely")
    parser.add_argument("--domain", default="", help="public app domain or full https base URL")
    parser.add_argument("--send-test", type=int, default=0, metavar="CHAT_ID")
    args = parser.parse_args()

    token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    secret = str(os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    domain = _base_url(
        args.domain
        or str(os.getenv("WEBHOOK_DOMAIN") or "")
        or str(os.getenv("APP_BASE_URL") or "")
        or str(os.getenv("RAILWAY_PUBLIC_DOMAIN") or "")
    )

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing", file=sys.stderr)
        return 2

    result: dict[str, object] = {
        "identity": _api(token, "getMe")["result"],
        "before": _api(token, "getWebhookInfo")["result"],
    }

    if args.repair:
        if not domain:
            print("ERROR: provide --domain or set WEBHOOK_DOMAIN/APP_BASE_URL/RAILWAY_PUBLIC_DOMAIN", file=sys.stderr)
            return 2
        if not secret:
            print("ERROR: TELEGRAM_WEBHOOK_SECRET is required for repair", file=sys.stderr)
            return 2
        endpoint = f"{domain}/telegram/webhook"
        result["repair"] = _api(
            token,
            "setWebhook",
            {
                "url": endpoint,
                "secret_token": secret,
                "allowed_updates": DEFAULT_ALLOWED,
                "drop_pending_updates": False,
                "max_connections": 20,
            },
        )["result"]
        result["after"] = _api(token, "getWebhookInfo")["result"]

    if args.send_test:
        result["send_test"] = _api(
            token,
            "sendMessage",
            {
                "chat_id": args.send_test,
                "text": "SignalRankAI Telegram transport test succeeded.",
            },
        )["result"]

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
