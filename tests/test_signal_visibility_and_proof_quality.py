from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_signals_command_uses_unresolved_received_signals_for_free_users():
    source = (ROOT / "signalrank_telegram" / "signal_commands.py").read_text(encoding="utf-8")

    free_branch = source.split("# FREE tier:", 1)[1].split("# PREMIUM/VIP:", 1)[0]
    assert "list_unresolved_signals_for_user" in free_branch
    assert "lookback_days=30" in free_branch
    assert "list_signals_sent_today" not in free_branch


def test_unresolved_signal_lookup_does_not_hide_received_signals_with_stale_flags():
    source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    helper = source.split("async def list_unresolved_signals_for_user", 1)[1].split("async def list_recent_signals_for_user", 1)[0]

    assert "~select(Outcome.id).where(Outcome.signal_id == Signal.signal_id).exists()" in helper
    assert "Signal.expired == False" not in helper
    assert "Signal.archived == False" not in helper


def test_leaderboard_requires_positive_expectancy_before_publishing():
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    leaderboard = source.split("async def leaderboard_command", 1)[1].split("# Conversation states", 1)[0]

    assert "LEADERBOARD_MIN_TRACKED_TRADES" in leaderboard
    assert "LEADERBOARD_MIN_WIN_RATE" in leaderboard
    assert "LEADERBOARD_MIN_AVG_R" in leaderboard
    assert "AVG(o.r_multiple) >= :min_avg_r" in leaderboard
    assert "* 100.0 >= :min_win_rate" in leaderboard
