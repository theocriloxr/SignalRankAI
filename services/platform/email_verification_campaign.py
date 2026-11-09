"""Ask existing users with an unverified email to verify it now (owner request, 9 Nov 2026).

"Ensure users verify their emails on setup, and those already in place that
haven't verified, let them verify it now." New sign-ups get the email at once
(web and Telegram paths). For accounts created before that, the owner runs
``/verify_email_campaign`` (counts only) and ``/verify_email_campaign send``.

Each eligible user (active account, email on file, not verified, no
verification email in the last ``cooldown_hours``) gets a fresh one-time link
by email; linked Telegram users also get a short message pointing to it.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

_ELIGIBLE_SQL = """
    SELECT u.id, u.telegram_user_id
    FROM users u
    WHERE u.primary_email IS NOT NULL AND u.primary_email <> ''
      AND u.email_verified_at IS NULL
      AND COALESCE(u.account_status, 'active') NOT IN ('deleted', 'suspended', 'closed', 'pending_deletion')
      AND NOT EXISTS (
          SELECT 1 FROM email_outbox e
          WHERE e.idempotency_key LIKE 'verify-email:' || u.id || ':%'
            AND e.created_at > NOW() - make_interval(hours => :cooldown)
      )
    ORDER BY u.id
    LIMIT :limit
"""

TELEGRAM_TEXT = ("📧 Please verify your email address. We just sent you a link; it expires in 30 minutes. "
                 "Verified emails get signal and trade updates by email and keep your account recoverable. "
                 "Didn't get it? Use Settings → Account security → Send verification email on the website.")


async def eligible_users(session: Any, *, cooldown_hours: int = 24, limit: int = 5000) -> list[tuple[int, int | None]]:
    rows = (await session.execute(text(_ELIGIBLE_SQL), {"cooldown": int(cooldown_hours), "limit": int(limit)})).all()
    return [(int(r[0]), int(r[1]) if r[1] is not None else None) for r in rows]


async def run_campaign(session: Any, *, base_url: str, send: bool, cooldown_hours: int = 24,
                       limit: int = 5000) -> dict[str, Any]:
    """Counts only unless ``send``; when sending, queues one verification email per user."""
    from services.platform.identity import AuthenticationError, request_email_verification

    users = await eligible_users(session, cooldown_hours=cooldown_hours, limit=limit)
    report: dict[str, Any] = {"eligible": len(users), "with_telegram": sum(1 for _, t in users if t),
                              "queued": 0, "skipped": 0, "telegram_ids": []}
    if not send:
        return report
    for user_id, telegram_id in users:
        try:
            async with session.begin_nested():
                await request_email_verification(session, user_id=user_id, base_url=base_url)
            report["queued"] += 1
            if telegram_id:
                report["telegram_ids"].append(telegram_id)
        except AuthenticationError:
            report["skipped"] += 1
    await session.commit()
    return report
