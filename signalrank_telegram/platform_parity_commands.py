"""Read-only Telegram views of October web workspace features (CX-CHAN-01).

/privacy reports the person's deletion review and points to the web Privacy
center; /account_merges lets owners and admins review pending Telegram/web
merges. Every mutation stays on the web/API path that enforces explicit
confirmation and a recent sign-in, which a Telegram message cannot prove.
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy import text
from telegram import Update
from telegram.ext import ContextTypes

from db.session import get_session
from signalrank_telegram.command_resilience import safe_command_error


def _web_url(path: str) -> str:
    base = str(
        os.getenv("APP_BASE_URL")
        or os.getenv("WEB_APP_URL")
        or "https://signalrank.criloxsolutions.com"
    ).rstrip("/")
    return f"{base}{path}"


def format_privacy_status(request: dict[str, Any] | None, retained: tuple[str, ...]) -> str:
    lines = ["🔒 Privacy and your data"]
    if request is None:
        lines.append("No account deletion review has been requested.")
    else:
        status = str(request.get("status") or "open")
        opened = str(request.get("created_at") or "")[:16]
        lines.append(f"Deletion review {str(request.get('ticket_id') or '')[:8]}: {status} (opened {opened} UTC).")
        if status != "closed":
            lines.append("Nothing is deleted until support completes the review.")
    lines.append("Kept even after deletion: " + "; ".join(retained) + ".")
    lines.append(
        "\nDownload your data export or request deletion in the web Privacy center: "
        f"{_web_url('/app/settings')}"
    )
    lines.append(
        "Exports are never sent through Telegram, and a deletion request needs a recent "
        "sign-in plus a typed confirmation there."
    )
    return "\n".join(lines)


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Read-only deletion-review status; export and deletion stay on the web."""
    if update.effective_user is None or update.message is None:
        return
    from services.platform.identity import ensure_telegram_user
    from services.platform.privacy import ACCOUNT_RETAINED_RECORDS, latest_deletion_request

    try:
        async with get_session(priority="interactive", label="telegram.privacy") as session:
            uid = await ensure_telegram_user(
                session,
                telegram_user_id=int(update.effective_user.id),
                username=getattr(update.effective_user, "username", None),
            )
            request = await latest_deletion_request(session, user_id=uid)
            await session.commit()
    except Exception as exc:
        await update.message.reply_text(safe_command_error("Could not load your privacy status.", exc))
        return
    await update.message.reply_text(format_privacy_status(request, ACCOUNT_RETAINED_RECORDS))


async def _telegram_operator_authority(session: Any, telegram_user_id: int) -> str | None:
    """Same OWNER/ADMIN rule as the web operator API, using the canonical tier."""
    from services.platform.operator_authority import operator_authority

    tier = (
        await session.execute(
            text("SELECT tier FROM users WHERE telegram_user_id=:tid LIMIT 1"),
            {"tid": int(telegram_user_id)},
        )
    ).scalar_one_or_none()
    return operator_authority(telegram_user_id=telegram_user_id, tier=tier)


def format_merge_list(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "🔗 Account merges\n\nNo merges are waiting for review."
    lines = [f"🔗 Account merges waiting for review: {len(rows)}"]
    for row in rows[:20]:
        lines.append(
            f"• {row.get('merge_id')} — keep #{row.get('canonical_user_id')}, "
            f"archive #{row.get('merged_user_id')} (since {str(row.get('created_at') or '')[:16]})"
        )
    if len(rows) > 20:
        lines.append(f"…and {len(rows) - 20} more.")
    lines.append("\nPreview one with /account_merges <merge_id>.")
    return "\n".join(lines)


def format_merge_plan(plan: dict[str, Any]) -> str:
    movable = {key: value for key, value in dict(plan.get("movable") or {}).items() if int(value or 0)}
    kept = dict(plan.get("kept_on_archived_account") or {})
    never = {key: value for key, value in dict(plan.get("never_moved") or {}).items() if int(value or 0)}
    failed = dict(plan.get("failed") or {})
    lines = [
        f"🔗 Merge {plan.get('merge_id')} (preview, nothing changed)",
        f"Keep account #{plan.get('canonical_user_id')}; archive #{plan.get('merged_user_id')}.",
        f"Rows that would move: {sum(int(value or 0) for value in movable.values())} across {len(movable)} references.",
    ]
    for key in sorted(movable, key=lambda name: -int(movable[name] or 0))[:8]:
        lines.append(f"- {key}: {movable[key]}")
    if kept:
        lines.append(f"Stay on the archived account (unique collision): {sum(int(v or 0) for v in kept.values())}")
    if never:
        lines.append("Never moved (credentials, sessions, audit): " + ", ".join(sorted(never)))
    if failed:
        lines.append("Could not be planned: " + ", ".join(sorted(failed)))
    if dict(plan.get("account_changes") or {}):
        lines.append("Account fields that would change: " + ", ".join(sorted(plan["account_changes"])))
    lines.append(
        "\nComplete the merge only from the web/API owner control or "
        "`python -m tools.complete_account_merge` (owner, recent sign-in, repeat the merge id)."
    )
    return "\n".join(lines)


async def account_merges_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owners and admins: list pending merges or preview one. Never applies a merge."""
    if update.effective_user is None or update.message is None:
        return
    merge_id = str((context.args or [""])[0]).strip()
    from services.platform.account_merge import MergeRefused, plan_account_merge

    try:
        async with get_session(priority="interactive", label="telegram.account_merges", timeout_seconds=15.0) as session:
            authority = await _telegram_operator_authority(session, int(update.effective_user.id))
            if authority not in {"OWNER", "ADMIN"}:
                await session.rollback()
                await update.message.reply_text("⛔ Operator access required.")
                return
            if not merge_id:
                rows = (await session.execute(text(
                    "SELECT merge_id, canonical_user_id, merged_user_id, created_at FROM account_merge_records "
                    "WHERE status = 'pending_review' ORDER BY created_at ASC LIMIT 200"
                ))).mappings().all()
                reply = format_merge_list([dict(row) for row in rows])
            else:
                try:
                    reply = format_merge_plan(await plan_account_merge(session, merge_id))
                except MergeRefused as exc:
                    reply = f"🔗 Merge {merge_id[:64]} cannot be merged: {exc}"
            await session.rollback()
    except Exception as exc:
        await update.message.reply_text(safe_command_error("Could not load account merges.", exc))
        return
    await update.message.reply_text(reply)


__all__ = [
    "account_merges_command", "format_merge_list", "format_merge_plan",
    "format_privacy_status", "privacy_command",
]
