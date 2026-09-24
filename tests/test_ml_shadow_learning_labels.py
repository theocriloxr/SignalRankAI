from ml.train_model import _normalize_shadow_outcome


def test_shadow_barrier_outcomes_feed_binary_learning():
    for value in ("win", "tp", "tp1", "tp2", "tp3", "partial_tp"):
        assert _normalize_shadow_outcome(value) == "win"
    for value in ("loss", "sl", "stop", "stop_loss"):
        assert _normalize_shadow_outcome(value) == "loss"


def test_ambiguous_shadow_outcomes_are_excluded():
    for value in ("", None, "ambiguous", "timeout", "expired", "other_outcome"):
        assert _normalize_shadow_outcome(value) is None
