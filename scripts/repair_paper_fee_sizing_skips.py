"""Repair legacy fee-sizing skips without opening trades or erasing evidence.

Dry-run is the default. ``--apply`` invalidates the placeholder position and,
only when the original delivery is still fresh and auto trading is enabled,
adds an explicit RETRY_PENDING attempt for the normal worker to reconsider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from core.delivery_state import CONFIRMED_DELIVERY_STATES
from core.paper_sizing import SIZING_POLICY_VERSION
from db.models import Outcome, PaperAccount, PaperPosition, PaperTradeAttempt, SignalDelivery
from db.session import get_session
from utils.timeutils import now_utc_naive

TERMINAL = {
    "tp", "tp3", "win", "sl", "loss", "stop", "stop_loss", "be",
    "breakeven", "break_even", "time_stop", "expired", "cancelled", "invalid",
}


async def run(apply: bool) -> int:
    now = now_utc_naive()
    max_age = max(1, int(os.getenv("PAPER_AUTO_ENTRY_MAX_AGE_SECONDS", "900") or 900))
    summary = {"mode": "apply" if apply else "dry_run", "affected": 0, "retry_queued": 0,
               "stale": 0, "auto_disabled": 0, "missing_proof": 0, "already_repaired": 0}
    details: list[dict[str, object]] = []
    async with get_session(priority="background", label="repair_paper_fee_sizing_skips") as session:
        result = await session.execute(
            select(PaperPosition, PaperAccount, SignalDelivery, Outcome)
            .join(PaperAccount, PaperAccount.id == PaperPosition.account_id)
            .outerjoin(SignalDelivery, SignalDelivery.id == PaperPosition.delivery_id)
            .outerjoin(Outcome, Outcome.signal_id == PaperPosition.signal_id)
            .where(
                func.lower(PaperPosition.status) == "skipped",
                func.lower(func.coalesce(PaperPosition.exit_reason, "")) == "insufficient_virtual_cash",
                PaperPosition.source == "delivered_signal",
            )
            .order_by(PaperPosition.created_at.asc())
        )
        for position, account, delivery, outcome in result.all():
            summary["affected"] += 1
            key = f"repair:fee-sizing-v2:{position.position_id}"[:128]
            exists = await session.scalar(
                select(PaperTradeAttempt.id).where(PaperTradeAttempt.idempotency_key == key)
            )
            if exists is not None:
                summary["already_repaired"] += 1
                continue
            proof = bool(
                delivery
                and delivery.sent_ok is True
                and str(delivery.delivery_state or "").lower() in CONFIRMED_DELIVERY_STATES
                and delivery.delivery_confirmed_at is not None
                and delivery.telegram_chat_id is not None
                and delivery.telegram_message_id is not None
            )
            deadline = (
                delivery.delivery_confirmed_at + timedelta(seconds=max_age)
                if proof else None
            )
            fresh = bool(deadline and now < deadline)
            terminal = str(getattr(outcome, "canonical_outcome", None) or getattr(outcome, "status", "") or "").lower() in TERMINAL
            queue_retry = bool(proof and fresh and account.auto_trade_enabled and not terminal)
            if not proof:
                reason = "fee_sizing_bug_invalidated_missing_delivery_proof"
                summary["missing_proof"] += 1
            elif not fresh or terminal:
                reason = "fee_sizing_bug_historical_not_fresh"
                summary["stale"] += 1
            elif not account.auto_trade_enabled:
                reason = "fee_sizing_bug_invalidated_auto_disabled"
                summary["auto_disabled"] += 1
            else:
                reason = "fee_sizing_bug_repair_queued"
                summary["retry_queued"] += 1
            details.append({"position_id": position.position_id, "signal_id": position.signal_id,
                            "action": reason, "would_retry": queue_retry})
            if not apply:
                continue

            position.status = "invalidated"
            position.exit_reason = reason[:64]
            position.updated_at = now
            meta = dict(position.meta or {})
            meta.update({"repair": "paper-fee-sizing-v2", "legacy_row_preserved": True,
                         "repaired_at": now.isoformat()})
            position.meta = meta
            if queue_retry:
                session.add(PaperTradeAttempt(
                    account_id=account.id,
                    user_id=account.user_id,
                    signal_id=position.signal_id,
                    delivery_id=delivery.id,
                    idempotency_key=key,
                    decision="RETRY_PENDING",
                    reason="fee_sizing_bug_repair_queued",
                    retryable=True,
                    attempt_number=1,
                    sizing_policy_version=SIZING_POLICY_VERSION,
                    first_attempt_at=now,
                    last_attempt_at=now,
                    next_retry_at=now,
                    retry_deadline=deadline,
                    meta={"repair_tool": "repair_paper_fee_sizing_skips.py",
                          "legacy_position_id": position.position_id, "opens_trade": False},
                ))
        if apply:
            await session.commit()
        else:
            await session.rollback()
    print(json.dumps({"summary": summary, "details": details}, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist invalidations and retry intents")
    return asyncio.run(run(parser.parse_args().apply))


if __name__ == "__main__":
    raise SystemExit(main())
