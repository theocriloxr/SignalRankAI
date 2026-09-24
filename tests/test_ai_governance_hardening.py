from pathlib import Path


def test_openai_defaults_use_current_cost_tiered_models_and_local_fallback() -> None:
    source = Path("services/openai_ai.py").read_text(encoding="utf-8")
    assert '"gpt-5.6-luna"' in source
    assert '"gpt-5.6-terra"' in source
    assert '"gpt-6-luna"' not in source
    assert '"gpt-6-sol"' not in source
    assert 'AI_PROVIDER_ORDER") or "openai,gemini,local"' in source
    assert '"store": False' in source
    assert '"prompt_cache_key"' in source
    assert "OPENAI_SIGNAL_CACHE_TTL_SECONDS" in source
    assert "OPENAI_DEEP_CACHE_TTL_SECONDS" in source


def test_evolution_agent_is_openai_first_and_cannot_auto_deploy() -> None:
    source = Path("core/evolution_agent.py").read_text(encoding="utf-8")
    openai_pos = source.index("proposal = await self._openai_proposal(context)")
    gemini_pos = source.index("proposal = await self._gemini_proposal(context)")
    local_pos = source.index("proposal = self._local_proposal(context)")
    assert openai_pos < gemini_pos < local_pos
    assert 'governed["auto_apply"] = False' in source
    assert 'governed["production_mutation"] = False' in source
    assert 'governed["requires_owner_approval"] = True' in source
    assert "Approve & Deploy" not in source
    assert "REVIEW ONLY — not applied, not deployed." in source


def test_weekly_improvements_notify_admins_but_remain_proposals_only() -> None:
    source = Path("services/continuous_improvement/scheduler.py").read_text(encoding="utf-8")
    assert "async def _notify_admins(report)" in source
    assert "CONTINUOUS_IMPROVEMENT_ADMIN_NOTIFY_ENABLED" in source
    assert "OWNER_IDS, ADMIN_IDS" in source
    assert "No change was auto-applied." in source
    assert '"production_mutation": False' in source
    assert '"admin_notification": admin_notification' in source


def test_ai_status_reports_cache_and_token_usage_without_key_material() -> None:
    source = Path("signalrank_telegram/commands.py").read_text(encoding="utf-8")
    start = source.index("async def ai_status_command")
    end = source.index("async def ai_test_command", start)
    block = source[start:end]
    assert 'status.get("cache")' in block
    assert 'status.get("usage_totals")' in block
    assert "OpenAI tokens this process" in block
    assert "provider_status()" in block
    assert "_api_key()" not in block
    assert 'os.getenv("OPENAI_API_KEY")' not in block


def test_ai_improve_is_registered_admin_only_review_workflow() -> None:
    commands = Path("signalrank_telegram/commands.py").read_text(encoding="utf-8")
    bot = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    catalog = Path("signalrank_telegram/command_catalog.py").read_text(encoding="utf-8")

    start = commands.index("async def ai_improve_command")
    end = commands.index("async def ai_test_command", start)
    block = commands[start:end]
    assert "_is_admin(update.effective_user.id)" in block
    assert "evolution_agent.trigger_system_audit(days=7)" in block
    assert "review only" in block.lower()
    assert "ai_improve_command," in bot
    assert 'CommandHandler("ai_improve"' in bot
    assert 'CommandSpec("ai_improve"' in catalog
