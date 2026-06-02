"""
core/evolution_agent.py - AI System Evolution Agent

This module enables Gemini to act as a "Lead Architect" for SignalRankAI.
It analyzes shadow trades, error logs, and system performance to propose code improvements.

Usage:
    from core.evolution_agent import EvolutionAgent
    
    agent = EvolutionAgent()
    proposal = await agent.trigger_system_audit(days=7)
    
    # To send proposal to admin:
    await agent.send_improvement_proposal(bot, proposal)
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("evolution_agent")

# Master prompt for Gemini as Lead Architect
EVOLUTION_SYSTEM_PROMPT = """You are the "Lead AI Architect" for SignalRankAI, an institutional-grade algorithmic trading system.

YOUR ROLE:
You are responsible for the continuous evolution, debugging, and optimization of the Python codebase. You analyze trade performance data (especially "Shadow Trades" that were rejected by validators) and system error logs to propose code upgrades.

YOUR OBJECTIVES:
1. Identify logic bottlenecks (e.g., drift thresholds that are too tight for current market volatility).
2. Fix runtime errors (e.g., API rate limits, missing imports, variable scope issues).
3. Discover and propose new Alpha strategies (e.g., fusing indicators, adding multi-timeframe confluence).

RULES OF ENGAGEMENT:
- Do NOT rewrite entire files. Provide only targeted, precise updates using Unified Diff format.
- All code changes MUST prioritize capital preservation and risk management.
- You do not execute code; you propose patches to the Human Admin for approval.
- Explain your reasoning clearly, concisely, and backed by the data provided in the prompt.

OUTPUT FORMAT (Strict JSON):
You must return a single JSON object with no markdown wrapping outside of the JSON block.

{
  "severity": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "target_file": "path/to/file.py",
  "reasoning": "A 1-2 sentence explanation for the human admin detailing WHY this patch is necessary and HOW it improves the system.",
  "code_diff": "@@ -10,3 +10,4 @@\\n- old_code = 1\\n+ new_code = 2\\n+ added_line = 3"
}"""


class EvolutionAgent:
    def __init__(self, model_name: str = "gemini-1.5-pro"):
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
    
    def _get_tail_logs(self, filepath: str, lines: int = 50) -> str:
        """Helper function to grab the latest logs."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except FileNotFoundError:
            return "No errors logged."
    
    async def _get_shadow_summary(self, days: int = 7) -> Dict[str, Any]:
        """Fetch shadow trade summary from database."""
        try:
            from db.session import get_session
            from db.models import Signal
            from sqlalchemy import select, func, and_
            from datetime import datetime
            
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            async with get_session() as session:
                # Count rejected signals
                rejected_query = select(
                    func.count(Signal.signal_id)
                ).where(
                    and_(
                        Signal.created_at >= cutoff,
                        Signal.status.in_(["rejected", "shadow_rejected", "invalidated"])
                    )
                )
                rejected_count = await session.scalar(rejected_query) or 0
                
                # Count total signals
                total_query = select(
                    func.count(Signal.signal_id)
                ).where(Signal.created_at >= cutoff)
                total_count = await session.scalar(total_query) or 0
                
                # Get top rejection reasons
                reason_query = select(
                    Signal.rejection_reason,
                    func.count(Signal.signal_id).label("count")
                ).where(
                    and_(
                        Signal.created_at >= cutoff,
                        Signal.rejection_reason.isnot(None)
                    )
                ).group_by(Signal.rejection_reason).order_by(func.count(Signal.signal_id).desc()).limit(5)
                
                reason_result = await session.execute(reason_query)
                top_rejections = [
                    {"reason": row[0] or "unknown", "count": row[1]}
                    for row in reason_result.fetchall()
                ]
                
                return {
                    "days": days,
                    "total_signals": total_count,
                    "rejected_signals": rejected_count,
                    "rejection_rate": rejected_count / max(1, total_count),
                    "top_rejections": top_rejections
                }
        except Exception as e:
            logger.warning(f"[evolution_agent] Could not fetch shadow summary: {e}")
            return {"days": days, "error": str(e)}
    
    async def trigger_system_audit(self, error_log_path: str = "app.log", days: int = 7) -> Optional[Dict[str, Any]]:
        """
        Gathers system context and asks Gemini for an architectural patch.
        
        Args:
            error_log_path: Path to the error log file
            days: Number of days to analyze
            
        Returns:
            JSON proposal from Gemini or None
        """
        if not self.api_key:
            logger.warning("[evolution_agent] No GEMINI_API_KEY configured")
            return None
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
        except ImportError:
            logger.warning("[evolution_agent] google-generativeai not installed")
            return None
        
        # 1. Gather Context
        recent_errors = self._get_tail_logs(error_log_path, lines=50)
        shadow_stats = await self._get_shadow_summary(days=days)
        
        # 2. Build the User Prompt
        prompt = f"""SYSTEM CONTEXT:
We are analyzing SignalRankAI system performance to identify improvements.

Recent Error Logs (last 50 lines):
{recent_errors}

Shadow Trade Performance (signals rejected but may have been profitable):
{json.dumps(shadow_stats, indent=2)}

TASK:
Based on the above data, identify ONE specific improvement that would increase signal delivery rate or fix a system issue.

If there are many rejections with "drift" or "stale" in the reason, propose increasing drift thresholds.
If there are import errors or missing modules, propose fixing imports.
If confidence is blocking too many signals, propose lowering confidence thresholds.

Generate a JSON patch following the output format specified in your instructions."""
        
        # 3. Call the Agent
        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=EVOLUTION_SYSTEM_PROMPT
            )
            
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # 4. Parse the JSON response
            # Handle potential markdown wrappers
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            patch_proposal = json.loads(response_text.strip())
            
            logger.info(f"[evolution_agent] Generated patch for {patch_proposal.get('target_file')}")
            return patch_proposal
            
        except json.JSONDecodeError as e:
            logger.error(f"[evolution_agent] Failed to parse JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"[evolution_agent] Failed to generate AI patch: {e}")
            return None
    
    async def send_improvement_proposal(self, bot, proposal: Dict[str, Any], admin_id: int) -> bool:
        """
        Send improvement proposal to admin for approval.
        
        Args:
            bot: Telegram bot instance
            proposal: The proposal from Gemini
            admin_id: Admin's Telegram user ID
            
        Returns:
            True if sent successfully
        """
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            message = (
                f"🛠 **AI ARCHITECT PROPOSAL**\n\n"
                f"**Severity:** {proposal.get('severity', 'MEDIUM')}\n"
                f"**Target:** `{proposal.get('target_file')}`\n\n"
                f"**Reasoning:** {proposal.get('reasoning')}\n\n"
                f"**Proposed Change:**\n```diff\n{proposal.get('code_diff')}\n```"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Approve & Deploy", callback_data="patch_approve")],
                [InlineKeyboardButton("❌ Reject", callback_data="patch_reject")]
            ]
            
            await bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return True
            
        except Exception as e:
            logger.error(f"[evolution_agent] Failed to send proposal: {e}")
            return False


# Global instance
evolution_agent = EvolutionAgent()
