#!/usr/bin/env python3
"""Static verifier for SignalRankAI v1.3.2 delivery/callback/monitor recovery."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *markers: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise SystemExit(f"FAIL {path}: missing {missing}")
    print(f"PASS {path}")


def main() -> int:
    require(
        "core/version.py",
        'CODE_VERSION = "1.3.2"',
        "v1.3.2-auto-delivery-callback-monitor-recovery-20260730",
    )
    require(
        "signalrank_telegram/bot.py",
        "_send_signal_card_for_user",
        "[open_signal_send_ok]",
        "Highest TP Reached",
        "Price Seen",
        "%H:%M:%S UTC",
        'RESEND_UNSENT_INTERVAL_SECONDS", "30"',
        'OUTCOME_NOTIFICATION_INTERVAL_SECONDS", "30"',
        'MONITOR_REFRESH_INTERVAL_SECONDS", "60"',
        "reply_markup=_build_monitor_keyboard(str(ref))",
    )
    require(
        "signalrank_telegram/callback_handlers.py",
        "Fallback monitor route that never overwrites the original signal card",
        "Fallback open-signal route; always renders a fresh authorized card",
        "_send_signal_card_for_user",
    )
    require(
        "engine/signal_lifecycle.py",
        "_lifecycle_notification_keyboard",
        '"disable_notification": False',
        'callback_data=f"open_signal_{ref}"',
        'callback_data=f"monitor_signal_{ref}"',
    )
    require(
        "railway_main.py",
        "unsent_signal_recovery_interval_too_high",
        "outcome_notification_interval_too_high",
        "monitor_refresh_interval_too_high",
        "resend_recovery_can_be_suppressed_by_fanout",
        "uncertified_rich_signal_delivery_enabled",
    )
    for profile in (
        "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example",
        "SignalRankAI_v1.3.2_Railway_Live_Financial_Activation.env.example",
    ):
        require(
            profile,
            "APP_VERSION=1.3.2",
            "APP_ENV=production",
            "DELIVERY_AUDIENCE_ALLOWLIST=",
            "RESEND_AUDIENCE_ALLOWLIST_ONLY=0",
            "ENGINE_DELIVERY_ASYNC_FANOUT=1",
            "RESEND_SKIP_WHEN_ENGINE_FANOUT_ACTIVE=0",
            "RESEND_UNSENT_INTERVAL_SECONDS=30",
            "OUTCOME_NOTIFICATION_INTERVAL_SECONDS=30",
            "MONITOR_REFRESH_INTERVAL_SECONDS=60",
            "TELEGRAM_SEND_MAX_ATTEMPTS=3",
            "TELEGRAM_RICH_MESSAGES_ENABLED=0",
        )
    print("overall=PASS release=v1.3.2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
