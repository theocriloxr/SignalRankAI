from pathlib import Path


def test_legacy_scheduler_registration_skips_when_canonical_jobs_exist():
    source = (Path(__file__).resolve().parents[1] / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")

    assert "def _schedule_bot_jobs" in source
    assert "canonical_ids" in source
    assert "resend_unsent_signals_job" in source
    assert "distribute_random_signals_to_free_users_job" in source
    assert "skipping legacy _schedule_bot_jobs registration" in source
