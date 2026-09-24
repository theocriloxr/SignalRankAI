"""Governed AI improvement adviser for SignalRankAI.

OpenAI is preferred for structured improvement proposals, Gemini is the
independent fallback, and deterministic local guidance is always available.
Nothing in this module applies code, changes trading thresholds, deploys, or
activates financial features. Proposals are evidence for an admin-reviewed
experiment only.
"""
from __future__ import annotations

from utils.timeutils import now_utc_naive

import json
import logging
import os
from datetime import timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger("evolution_agent")


EVOLUTION_SYSTEM_PROMPT = """You are an improvement reviewer for SignalRankAI.
Use only the supplied aggregate evidence and error excerpts. Propose exactly one
small reversible improvement. Never claim a future win rate. Never weaken data
freshness, security, risk, exposure, calibration, execution kill switches,
owner approval, or forward-testing gates merely to increase signal volume.
Any trading-behavior change must include a test plan and forward test.
Never apply or deploy changes yourself."""


class EvolutionAgent:
    def __init__(self, model_name: str | None = None):
        self.model_name = str(
            model_name
            or os.getenv("GEMINI_EVOLUTION_MODEL")
            or os.getenv("GEMINI_MODEL")
            or "gemini-3.8-flash"
        ).strip()

    def _get_tail_logs(self, filepath: str, lines: int = 50) -> str:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as handle:
                return "".join(handle.readlines()[-max(1, min(int(lines), 200)):])
        except FileNotFoundError:
            return "No local error log file was found."
        except Exception as exc:
            return f"Log read unavailable: {type(exc).__name__}"

    async def _get_shadow_summary(self, days: int = 7) -> Dict[str, Any]:
        """Fetch aggregate shadow/rejection evidence without user-level data."""
        try:
            from db.session import get_session
            from db.models import Signal
            from sqlalchemy import select, func, and_

            cutoff = now_utc_naive() - timedelta(days=max(1, min(int(days), 90)))
            async with get_session(
                priority="analytics",
                label="evolution_shadow_summary",
                timeout_seconds=30.0,
                drop_if_busy=False,
            ) as session:
                rejected_query = select(func.count(Signal.signal_id)).where(
                    and_(
                        Signal.created_at >= cutoff,
                        Signal.status.in_(["rejected", "shadow_rejected", "invalidated"]),
                    )
                )
                total_query = select(func.count(Signal.signal_id)).where(Signal.created_at >= cutoff)
                reason_query = (
                    select(Signal.rejection_reason, func.count(Signal.signal_id).label("count"))
                    .where(
                        and_(
                            Signal.created_at >= cutoff,
                            Signal.rejection_reason.isnot(None),
                        )
                    )
                    .group_by(Signal.rejection_reason)
                    .order_by(func.count(Signal.signal_id).desc())
                    .limit(8)
                )
                rejected_count = int(await session.scalar(rejected_query) or 0)
                total_count = int(await session.scalar(total_query) or 0)
                reason_result = await session.execute(reason_query)
                top_rejections = [
                    {"reason": str(row[0] or "unknown")[:180], "count": int(row[1] or 0)}
                    for row in reason_result.fetchall()
                ]
                await session.rollback()
            return {
                "days": max(1, min(int(days), 90)),
                "total_signals": total_count,
                "rejected_signals": rejected_count,
                "rejection_rate": rejected_count / max(1, total_count),
                "top_rejections": top_rejections,
            }
        except Exception as exc:
            logger.warning("[evolution_agent] shadow summary unavailable error=%s", type(exc).__name__)
            return {"days": days, "error": type(exc).__name__}

    @staticmethod
    def _govern(proposal: Dict[str, Any], provider: str) -> Dict[str, Any]:
        governed = dict(proposal or {})
        governed["provider"] = provider
        governed["requires_owner_approval"] = True
        governed["requires_forward_test"] = bool(governed.get("requires_forward_test", True))
        governed["auto_apply"] = False
        governed["production_mutation"] = False
        governed["created_at"] = now_utc_naive().isoformat()
        if "test_plan" not in governed or not isinstance(governed.get("test_plan"), list):
            governed["test_plan"] = [
                "Add or update deterministic regression tests.",
                "Run backtest/walk-forward or replay evidence where trading behavior changes.",
                "Run shadow/paper/staging validation before production eligibility.",
            ]
        return governed

    async def _openai_proposal(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            from services.openai_ai import evolution_proposal, openai_available
            if not openai_available():
                return None
            result = await evolution_proposal(context)
            if not result.get("ok"):
                return None
            data = result.get("data")
            if not isinstance(data, dict):
                return None
            governed = self._govern(data, "openai")
            governed["model"] = str(result.get("model") or "")[:96]
            governed["usage"] = dict(result.get("usage") or {}) if isinstance(result.get("usage"), dict) else {}
            governed["cache_hit"] = bool(result.get("cache_hit"))
            return governed
        except Exception as exc:
            logger.info("[evolution_agent] OpenAI proposal unavailable error=%s", type(exc).__name__)
            return None

    async def _gemini_proposal(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            from services.gemini_ml import _call_gemini, gemini_available
            if not gemini_available():
                return None
            prompt = (
                EVOLUTION_SYSTEM_PROMPT
                + "\nReturn JSON only with keys severity, target_file, reasoning, code_diff, "
                  "test_plan, requires_forward_test, requires_owner_approval.\nEVIDENCE:\n"
                + json.dumps(context, default=str)[:14000]
            )
            raw = await _call_gemini(prompt, max_tokens=1200)
            if not raw:
                return None
            start, end = raw.find("{"), raw.rfind("}")
            candidate = json.loads(raw[start : end + 1] if start >= 0 and end > start else raw)
            if not isinstance(candidate, dict):
                return None
            candidate.setdefault("requires_forward_test", True)
            candidate.setdefault("requires_owner_approval", True)
            governed = self._govern(candidate, "gemini")
            governed["model"] = self.model_name
            return governed
        except Exception as exc:
            logger.info("[evolution_agent] Gemini proposal unavailable error=%s", type(exc).__name__)
            return None

    @staticmethod
    def _local_proposal(context: Dict[str, Any]) -> Dict[str, Any]:
        shadow = dict(context.get("shadow_summary") or {})
        error_excerpt = str(context.get("recent_errors") or "")
        reasons = list(shadow.get("top_rejections") or [])
        if "error" in error_excerpt.lower() or "traceback" in error_excerpt.lower():
            reasoning = (
                "Recent runtime errors are present. Triage the highest-frequency reproducible "
                "failure and add a regression test before changing trading thresholds."
            )
            target = "runtime/error-path-review"
        elif reasons:
            top = reasons[0]
            reasoning = (
                f"The leading rejection bucket is {top.get('reason', 'unknown')} "
                f"({int(top.get('count') or 0)} observations). Compare rejected-signal outcomes "
                "before proposing any threshold change."
            )
            target = "engine/quality-gates-review"
        else:
            reasoning = (
                "No external AI provider is available. Preserve current risk settings and "
                "continue collecting outcome/shadow evidence for the next governed review."
            )
            target = "no-code-change"
        return EvolutionAgent._govern(
            {
                "severity": "LOW",
                "target_file": target,
                "reasoning": reasoning,
                "code_diff": "",
                "test_plan": [
                    "Reproduce the issue or evidence gap.",
                    "Add deterministic regression coverage.",
                    "Use shadow/paper/staging evidence before production change.",
                ],
                "requires_forward_test": True,
            },
            "local",
        )

    async def trigger_system_audit(
        self,
        error_log_path: str = "app.log",
        days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        """Return one governed proposal using OpenAI -> Gemini -> local fallback."""
        context = {
            "review_kind": "signalrank_system_improvement",
            "recent_errors": self._get_tail_logs(error_log_path, lines=50),
            "shadow_summary": await self._get_shadow_summary(days=days),
            "guardrails": {
                "production_mutation": False,
                "requires_owner_approval": True,
                "requires_forward_test": True,
                "do_not_optimize_win_rate_alone": True,
            },
        }
        proposal = await self._openai_proposal(context)
        if proposal is None:
            proposal = await self._gemini_proposal(context)
        if proposal is None:
            proposal = self._local_proposal(context)
        logger.info(
            "[evolution_agent] proposal provider=%s target=%s",
            proposal.get("provider"),
            proposal.get("target_file"),
        )
        return proposal

    async def send_improvement_proposal(
        self,
        bot,
        proposal: Dict[str, Any],
        admin_id: int,
    ) -> bool:
        """Send an admin review card. This function never deploys a patch."""
        try:
            provider = str(proposal.get("provider") or "local")
            tests = list(proposal.get("test_plan") or [])
            test_lines = "\n".join(f"- {str(item)[:220]}" for item in tests[:5]) or "- Add regression coverage."
            diff = str(proposal.get("code_diff") or "").strip()
            diff_note = diff[:1600] if diff else "(No direct patch; investigation/experiment proposal.)"
            message = (
                "🛠 AI IMPROVEMENT PROPOSAL\n\n"
                f"Provider: {provider}\n"
                f"Severity: {proposal.get('severity', 'LOW')}\n"
                f"Target: {proposal.get('target_file', 'review')}\n\n"
                f"Reasoning: {str(proposal.get('reasoning') or '')[:1200]}\n\n"
                f"Proposed diff / task:\n{diff_note}\n\n"
                f"Required validation:\n{test_lines}\n\n"
                "Status: REVIEW ONLY — not applied, not deployed.\n"
                "Owner approval + tests + forward/shadow/staging evidence are required."
            )
            await bot.send_message(chat_id=admin_id, text=message)
            return True
        except Exception as exc:
            logger.error("[evolution_agent] admin proposal delivery failed error=%s", type(exc).__name__)
            return False


evolution_agent = EvolutionAgent()
