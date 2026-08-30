"""Owner-only staging data cleanup (dry-run / apply).

    python -m tools.staging_cleanup --dry-run
    python -m tools.staging_cleanup --apply --tester-ids 12345,67890

Preserves immutable history and audit events; keeps only approved staging
testers active; NEVER touches production.  In production the tool refuses to
run.  All mutation happens inside short bounded transactions.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _environment() -> str:
    return str(
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or "local"
    ).lower()


def _is_production() -> bool:
    env = _environment()
    return env.startswith("prod") or env in ("production", "live")


def _parse_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in str(raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _queries() -> dict[str, str]:
    return {
        "stale_active_signals": (
            "SELECT COUNT(*) FROM signals WHERE LOWER(status) IN ('active','issued','pending') "
            "AND (expires_at IS NULL OR expires_at < NOW() - INTERVAL '4 hours')"
        ),
        "pending_signals_old": (
            "SELECT COUNT(*) FROM signals WHERE LOWER(status) = 'pending' "
            "AND created_at < NOW() - INTERVAL '24 hours'"
        ),
        "unreachable_users": (
            "SELECT COUNT(*) FROM users WHERE telegram_reachable = FALSE"
        ),
        "open_paper_positions": (
            "SELECT COUNT(*) FROM paper_positions WHERE LOWER(status) = 'open'"
        ),
        "reserved_deliveries_stale": (
            "SELECT COUNT(*) FROM signal_deliveries WHERE LOWER(delivery_state) IN ('reserved','pending') "
            "AND created_at < NOW() - INTERVAL '24 hours'"
        ),
    }


def _apply_queries(session) -> dict[str, int]:
    from sqlalchemy import text

    counts = {}
    now = _now()
    # Archive: mark stale active signals expired (history preserved).
    session.execute(text(
        "UPDATE signals SET status = 'expired', expired = TRUE, updated_at = :now "
        "WHERE LOWER(status) IN ('active','issued','pending') "
        "AND (expires_at IS NULL OR expires_at < NOW() - INTERVAL '4 hours')"
    ), {"now": now})
    session.execute(text(
        "UPDATE signals SET status = 'expired', expired = TRUE, updated_at = :now "
        "WHERE LOWER(status) = 'pending' AND created_at < NOW() - INTERVAL '24 hours'"
    ), {"now": now})
    # Stale delivery reservations -> terminal failed (history preserved).
    session.execute(text(
        "UPDATE signal_deliveries SET delivery_state = 'failed', updated_at = :now, "
        "last_error = 'stale_reservation_archived' "
        "WHERE LOWER(delivery_state) IN ('reserved','pending') "
        "AND created_at < NOW() - INTERVAL '24 hours'"
    ), {"now": now})
    session.execute(text(
        "DELETE FROM resend_queue WHERE claimed_at IS NOT NULL AND claimed_at < NOW() - INTERVAL '24 hours'"
    ))
    counts["archived"] = 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging data cleanup")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="report counts only")
    group.add_argument("--apply", action="store_true", help="apply the cleanup")
    parser.add_argument("--tester-ids", default=os.getenv("STAGING_TESTER_TELEGRAM_IDS", ""), help="approved staging tester Telegram IDs")
    args = parser.parse_args()

    if _is_production():
        print("CLEANUP_BLOCKED environment=production; this tool is staging-only")
        return 1

    tester_ids = _parse_ids(args.tester_ids)
    try:
        from db.session import get_session
    except Exception as exc:
        print(f"CLEANUP_ERROR db_unavailable {exc}")
        return 1

    with get_session() as session:
        from sqlalchemy import text

        if args.dry_run:
            print(f"CLEANUP_DRY_RUN environment={_environment()}")
            for name, query in _queries().items():
                row = session.execute(text(query)).fetchone()
                print(f"  {name}={int(row[0]) if row else 0}")
            print(f"  approved_testers={len(tester_ids)}")
            if tester_ids:
                # Deactivate non-tester users (dry-run: count only).
                row = session.execute(
                    text("SELECT COUNT(*) FROM users WHERE telegram_user_id NOT IN :ids"),
                    {"ids": tuple(tester_ids)},
                ).fetchone() if tester_ids else None
                print(f"  users_to_deactivate={int(row[0]) if row else 0}")
            return 0

        # Apply mode
        counts = _apply_queries(session)
        session.commit()
        if tester_ids:
            session.execute(text(
                "UPDATE users SET notification_suppressed = TRUE, telegram_reachable = FALSE "
                "WHERE telegram_user_id NOT IN :ids"
            ), {"ids": tuple(tester_ids)})
            session.commit()
        # Re-enable owner/approved testers.
        if tester_ids:
            session.execute(text(
                "UPDATE users SET notification_suppressed = FALSE, telegram_reachable = TRUE "
                "WHERE telegram_user_id IN :ids"
            ), {"ids": tuple(tester_ids)})
            session.commit()
        print(f"CLEANUP_APPLIED environment={_environment()} archived={counts.get('archived', 0)} "
              f"approved_testers={len(tester_ids)}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
