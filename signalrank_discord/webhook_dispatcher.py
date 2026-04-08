from __future__ import annotations

import os
import requests


def dispatch_signal_webhook(text: str, tier: str = "premium") -> bool:
    """Send a signal payload to Discord webhook by tier channel."""
    tier_key = str(tier or "premium").strip().upper()
    url = os.getenv(f"DISCORD_WEBHOOK_{tier_key}") or os.getenv("DISCORD_WEBHOOK_DEFAULT")
    if not url:
        return False
    try:
        resp = requests.post(url, json={"content": text}, timeout=8)
        return 200 <= int(resp.status_code) < 300
    except Exception:
        return False
