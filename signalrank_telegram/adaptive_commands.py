from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import text

from config import ADMIN_IDS, OWNER_IDS
from core.redis_state import state
from db.session import get_session
from engine.adaptive.promotion import evaluate_profile_promotion
from engine.adaptive.repository import invalidate_profile_cache, publish_approved_profiles

logger = logging.getLogger(__name__)


def _privileged_ids() -> set[int]:
    return {int(value) for value in (OWNER_IDS or set())} | {int(value) for value in (ADMIN_IDS or set())}


def _actor_id(update: Any) -> int:
    return int(getattr(getattr(update, "effective_user", None), "id", 0) or 0)


async def _require_owner(update: Any) -> bool:
    actor = _actor_id(update)
    if actor and actor in _privileged_ids():
        return True
    # Hidden owner surface: do not disclose operational details to unauthorised users.
    return False


async def _reply(update: Any, message: str) -> None:
    target = getattr(update, "effective_message", None) or getattr(update, "message", None)
    if target is not None:
        await target.reply_text(message)


def _args(context: Any) -> list[str]:
    return [str(value).strip() for value in (getattr(context, "args", None) or []) if str(value).strip()]


async def adaptive_status_command(update: Any, context: Any) -> None:
    if not await _require_owner(update):
        return
    args = _args(context)
    asset = args[0].upper() if args else None
    paused = str(state.get_sync("adaptive:optimisation:paused") or "0").lower() in {"1", "true", "yes", "on"}
    async with get_session(priority="interactive", label="adaptive.command.status", timeout_seconds=4) as session:
        profile_rows = (
            await session.execute(
                text(
                    """
                    SELECT profile_id,asset,version,state,is_current,sample_size,data_sufficiency_score,
                           metadata->>'dataset_version' AS dataset_version,
                           metadata->>'feature_version' AS feature_version,
                           metadata->'walk_forward' AS walk_forward
                    FROM adaptive_asset_profiles
                    WHERE (:asset IS NULL OR asset=:asset)
                    ORDER BY asset,is_current DESC,version DESC
                    LIMIT 12
                    """
                ),
                {"asset": asset},
            )
        ).mappings().all()
        latest_run = (
            await session.execute(
                text(
                    """
                    SELECT run_id,status,mode,dataset_version,feature_version,started_at,completed_at,summary
                    FROM adaptive_optimisation_runs
                    ORDER BY started_at DESC LIMIT 1
                    """
                )
            )
        ).mappings().first()
        dataset_count = int((await session.execute(text("SELECT COUNT(*) FROM adaptive_dataset_versions"))).scalar() or 0)
        wfo_count = int((await session.execute(text("SELECT COUNT(*) FROM adaptive_walk_forward_runs"))).scalar() or 0)

    lines = [
        "🧠 Adaptive Strategy Intelligence",
        f"Learning: {'PAUSED' if paused else 'ENABLED'}",
        f"Dataset versions: {dataset_count}",
        f"Walk-forward runs: {wfo_count}",
    ]
    if latest_run:
        lines.append(
            f"Latest optimisation: {latest_run['status']} • {latest_run['mode']} • {str(latest_run['run_id'])[:8]}"
        )
    if profile_rows:
        lines.append("\nProfiles:")
        for row in profile_rows:
            wfo = row.get("walk_forward") or {}
            if isinstance(wfo, str):
                try:
                    wfo = json.loads(wfo)
                except Exception:
                    wfo = {}
            lines.append(
                f"• {row['asset']} v{row['version']} {row['state']}"
                f"{' CURRENT' if row['is_current'] else ''} • n={row['sample_size']}"
                f" • WFO {int(wfo.get('positive_folds') or 0)}/{int(wfo.get('fold_count') or 0)}"
            )
    else:
        lines.append("No matching adaptive profiles yet.")
    await _reply(update, "\n".join(lines))


async def adaptive_pause_command(update: Any, context: Any) -> None:
    if not await _require_owner(update):
        return
    state.set_sync("adaptive:optimisation:paused", "1")
    await _reply(update, "⏸ Adaptive optimisation paused. Runtime risk and approved profile selection remain unchanged.")


async def adaptive_resume_command(update: Any, context: Any) -> None:
    if not await _require_owner(update):
        return
    state.set_sync("adaptive:optimisation:paused", "0")
    await _reply(update, "▶️ Adaptive optimisation resumed. New candidates still begin in SHADOW and require promotion evidence.")


async def adaptive_promote_command(update: Any, context: Any) -> None:
    if not await _require_owner(update):
        return
    args = _args(context)
    if len(args) != 2:
        await _reply(update, "Usage: /adaptive_promote <profile_id> <FORWARD_TEST|CANARY|LIMITED_LIVE>")
        return
    profile_id, target = args[0], args[1].upper()
    actor = _actor_id(update)
    asset: str | None = None
    result_reasons: tuple[str, ...] = ()
    promoted = False

    async with get_session(priority="interactive", label="adaptive.command.promote", timeout_seconds=6) as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT profile_id,asset,version,state,is_current,metadata
                    FROM adaptive_asset_profiles WHERE profile_id=:profile_id FOR UPDATE
                    """
                ),
                {"profile_id": profile_id},
            )
        ).mappings().first()
        if not row:
            await _reply(update, "Profile not found.")
            return
        asset = str(row["asset"])
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        wfo = metadata.get("walk_forward") or {}
        metrics = {
            "sample_size": wfo.get("sample_size") or metadata.get("sample_size") or 0,
            "positive_wfo_folds": wfo.get("positive_folds") or 0,
            "expectancy_r": wfo.get("expectancy_r") or 0,
            "profit_factor": wfo.get("profit_factor") or 0,
            "max_drawdown_r": wfo.get("max_drawdown_r") if wfo.get("max_drawdown_r") is not None else 999,
            "brier_score": metadata.get("brier_score"),
            "leakage_checks_passed": wfo.get("leakage_checks_passed", False),
        }
        gate = evaluate_profile_promotion(
            metrics,
            human_approved=True,
            target_state=target,
            current_state=str(row["state"]),
        )
        result_reasons = gate.reasons
        dataset_version = str(metadata.get("dataset_version") or "unknown")
        idempotency_key = hashlib.sha256(
            f"adaptive-promote:{profile_id}:{target}:{dataset_version}:{actor}".encode()
        ).hexdigest()
        if gate.eligible:
            previous_current = None
            if target in {"CANARY", "LIMITED_LIVE"}:
                previous_current = (
                    await session.execute(
                        text(
                            """
                            SELECT profile_id FROM adaptive_asset_profiles
                            WHERE asset=:asset AND is_current=TRUE AND profile_id<>:profile_id
                            ORDER BY version DESC LIMIT 1
                            """
                        ),
                        {"asset": asset, "profile_id": profile_id},
                    )
                ).scalar()
                await session.execute(
                    text("UPDATE adaptive_asset_profiles SET is_current=FALSE,updated_at=NOW() WHERE asset=:asset AND is_current=TRUE"),
                    {"asset": asset},
                )
            await session.execute(
                text(
                    """
                    UPDATE adaptive_asset_profiles
                    SET state=:target,
                        is_current=:is_current,
                        rollback_profile_id=COALESCE(:rollback_profile_id,rollback_profile_id),
                        metadata=jsonb_set(COALESCE(metadata,'{}'::jsonb),'{last_human_approver}',to_jsonb(CAST(:actor AS BIGINT)),TRUE),
                        updated_at=NOW()
                    WHERE profile_id=:profile_id
                    """
                ),
                {
                    "target": target,
                    "is_current": target in {"CANARY", "LIMITED_LIVE"},
                    "rollback_profile_id": previous_current,
                    "actor": actor,
                    "profile_id": profile_id,
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO adaptive_promotion_events(
                        profile_id,from_state,to_state,decision,reasons,metrics,actor_telegram_user_id,idempotency_key
                    ) VALUES(
                        :profile_id,:from_state,:to_state,'APPROVED',CAST(:reasons AS JSONB),CAST(:metrics AS JSONB),:actor,:key
                    ) ON CONFLICT(idempotency_key) DO NOTHING
                    """
                ),
                {
                    "profile_id": profile_id,
                    "from_state": row["state"],
                    "to_state": target,
                    "reasons": json.dumps([]),
                    "metrics": json.dumps(metrics),
                    "actor": actor,
                    "key": idempotency_key,
                },
            )
            promoted = True
        else:
            await session.execute(
                text(
                    """
                    INSERT INTO adaptive_promotion_events(
                        profile_id,from_state,to_state,decision,reasons,metrics,actor_telegram_user_id,idempotency_key
                    ) VALUES(
                        :profile_id,:from_state,:to_state,'REJECTED',CAST(:reasons AS JSONB),CAST(:metrics AS JSONB),:actor,:key
                    ) ON CONFLICT(idempotency_key) DO NOTHING
                    """
                ),
                {
                    "profile_id": profile_id,
                    "from_state": row["state"],
                    "to_state": target,
                    "reasons": json.dumps(list(gate.reasons)),
                    "metrics": json.dumps(metrics),
                    "actor": actor,
                    "key": idempotency_key,
                },
            )
        await session.commit()

    if promoted:
        await publish_approved_profiles()
        await _reply(update, f"✅ {profile_id} promoted to {target}. Risk, delivery, and execution gates remain authoritative.")
    else:
        await _reply(update, "❌ Promotion blocked:\n- " + "\n- ".join(result_reasons))


async def adaptive_suspend_command(update: Any, context: Any) -> None:
    if not await _require_owner(update):
        return
    args = _args(context)
    if not args:
        await _reply(update, "Usage: /adaptive_suspend <profile_id> [reason]")
        return
    profile_id = args[0]
    reason = " ".join(args[1:])[:500] or "owner_suspension"
    actor = _actor_id(update)
    asset: str | None = None
    async with get_session(priority="interactive", label="adaptive.command.suspend", timeout_seconds=6) as session:
        row = (
            await session.execute(
                text("SELECT asset,state FROM adaptive_asset_profiles WHERE profile_id=:profile_id FOR UPDATE"),
                {"profile_id": profile_id},
            )
        ).mappings().first()
        if not row:
            await _reply(update, "Profile not found.")
            return
        asset = str(row["asset"])
        await session.execute(
            text("UPDATE adaptive_asset_profiles SET state='SUSPENDED',is_current=FALSE,updated_at=NOW(),metadata=jsonb_set(COALESCE(metadata,'{}'::jsonb),'{suspension_reason}',to_jsonb(CAST(:reason AS TEXT)),TRUE) WHERE profile_id=:profile_id"),
            {"reason": reason, "profile_id": profile_id},
        )
        key = hashlib.sha256(f"adaptive-suspend:{profile_id}:{reason}:{actor}".encode()).hexdigest()
        await session.execute(
            text("INSERT INTO adaptive_promotion_events(profile_id,from_state,to_state,decision,reasons,metrics,actor_telegram_user_id,idempotency_key) VALUES(:profile_id,:from_state,'SUSPENDED','SUSPENDED',CAST(:reasons AS JSONB),'{}'::jsonb,:actor,:key) ON CONFLICT(idempotency_key) DO NOTHING"),
            {"profile_id": profile_id, "from_state": row["state"], "reasons": json.dumps([reason]), "actor": actor, "key": key},
        )
        await session.commit()
    if asset:
        invalidate_profile_cache(asset)
    await _reply(update, f"🛑 {profile_id} suspended. Runtime falls back to the neutral baseline until rollback or a safe replacement.")


async def adaptive_rollback_command(update: Any, context: Any) -> None:
    if not await _require_owner(update):
        return
    args = _args(context)
    if not args:
        await _reply(update, "Usage: /adaptive_rollback <asset>")
        return
    asset = args[0].upper()
    actor = _actor_id(update)
    target_profile: str | None = None
    current_profile: str | None = None
    async with get_session(priority="interactive", label="adaptive.command.rollback", timeout_seconds=6) as session:
        current = (
            await session.execute(
                text("SELECT profile_id,state,rollback_profile_id FROM adaptive_asset_profiles WHERE asset=:asset AND is_current=TRUE FOR UPDATE"),
                {"asset": asset},
            )
        ).mappings().first()
        if not current:
            await _reply(update, "No current adaptive profile exists for that asset.")
            return
        current_profile = str(current["profile_id"])
        target_profile = current.get("rollback_profile_id")
        if not target_profile:
            target_profile = (
                await session.execute(
                    text("SELECT profile_id FROM adaptive_asset_profiles WHERE asset=:asset AND profile_id<>:current AND state IN ('CANARY','LIMITED_LIVE','APPROVED') ORDER BY version DESC LIMIT 1"),
                    {"asset": asset, "current": current_profile},
                )
            ).scalar()
        if not target_profile:
            await _reply(update, "Rollback blocked: no previously approved runtime profile is available.")
            return
        await session.execute(
            text("UPDATE adaptive_asset_profiles SET is_current=FALSE,state='ROLLED_BACK',updated_at=NOW() WHERE profile_id=:profile_id"),
            {"profile_id": current_profile},
        )
        await session.execute(
            text("UPDATE adaptive_asset_profiles SET is_current=TRUE,updated_at=NOW() WHERE profile_id=:profile_id AND state IN ('CANARY','LIMITED_LIVE','APPROVED')"),
            {"profile_id": target_profile},
        )
        key = hashlib.sha256(f"adaptive-rollback:{asset}:{current_profile}:{target_profile}:{actor}".encode()).hexdigest()
        await session.execute(
            text("INSERT INTO adaptive_promotion_events(profile_id,from_state,to_state,decision,reasons,metrics,actor_telegram_user_id,idempotency_key) VALUES(:profile_id,:from_state,'ROLLED_BACK','ROLLED_BACK',CAST(:reasons AS JSONB),'{}'::jsonb,:actor,:key) ON CONFLICT(idempotency_key) DO NOTHING"),
            {"profile_id": current_profile, "from_state": current["state"], "reasons": json.dumps([f"restored:{target_profile}"]), "actor": actor, "key": key},
        )
        await session.commit()
    await publish_approved_profiles()
    await _reply(update, f"↩️ {asset} rolled back from {current_profile} to {target_profile}.")
