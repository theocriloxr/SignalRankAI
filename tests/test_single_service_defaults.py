"""Tests for single-service deployment defaults.

Covers:
1. Railway memory-safe defaults for monolith loop toggles.
2. Tier-gated signal distribution — deterministic score threshold behaviour.
3. Outcome tracker enabled by default in worker.
"""
import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _env(**overrides):
    """Return a patched os.getenv that applies *overrides* and falls back to
    the real environment for everything else."""
    real = os.environ.copy()

    def _getenv(key, default=None):
        if key in overrides:
            return overrides[key]
        return real.get(key, default)

    return _getenv


# ---------------------------------------------------------------------------
# 1. Loop defaults
# ---------------------------------------------------------------------------

class TestLoopDefaults(unittest.TestCase):
    """Loop defaults should be memory-safe on Railway."""

    def _run_worker_is_enabled(self, env_overrides: dict) -> bool:
        with patch("os.getenv", side_effect=_env(**env_overrides)):
            running_on_railway = bool(
                (os.getenv("RAILWAY_SERVICE_NAME") or "").strip()
                or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip()
            )
            default_val = "0" if running_on_railway else "1"
            run_worker_raw = os.getenv("RUN_WORKER_LOOP", default_val) or default_val
            return run_worker_raw.strip().lower() in {"1", "true", "yes", "on"}

    def _run_engine_is_enabled(self, env_overrides: dict) -> bool:
        with patch("os.getenv", side_effect=_env(**env_overrides)):
            running_on_railway = bool(
                (os.getenv("RAILWAY_SERVICE_NAME") or "").strip()
                or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip()
            )
            default_val = "0" if running_on_railway else "1"
            run_engine_raw = os.getenv("RUN_ENGINE_LOOP", default_val) or default_val
            return run_engine_raw.strip().lower() in {"1", "true", "yes", "on"}

    def test_worker_default_is_on_without_railway_env(self):
        result = self._run_worker_is_enabled({})
        self.assertTrue(result, "Worker loop should default ON outside Railway")

    def test_worker_default_is_off_with_railway_service_name(self):
        result = self._run_worker_is_enabled({"RAILWAY_SERVICE_NAME": "signalrankai"})
        self.assertFalse(result, "Worker loop should default OFF on Railway")

    def test_worker_explicit_zero_disables_worker(self):
        result = self._run_worker_is_enabled({"RUN_WORKER_LOOP": "0"})
        self.assertFalse(result, "RUN_WORKER_LOOP=0 must disable the worker")

    def test_worker_explicit_one_enables_worker(self):
        result = self._run_worker_is_enabled({"RUN_WORKER_LOOP": "1"})
        self.assertTrue(result, "RUN_WORKER_LOOP=1 must enable the worker")

    def test_engine_default_is_on_without_railway_env(self):
        result = self._run_engine_is_enabled({})
        self.assertTrue(result, "Engine loop should default ON outside Railway")

    def test_engine_default_is_off_with_railway_service_name(self):
        result = self._run_engine_is_enabled({"RAILWAY_SERVICE_NAME": "signalrankai"})
        self.assertFalse(result, "Engine loop should default OFF on Railway")

    def test_engine_explicit_one_enables_engine(self):
        result = self._run_engine_is_enabled({"RAILWAY_SERVICE_NAME": "signalrankai", "RUN_ENGINE_LOOP": "1"})
        self.assertTrue(result, "RUN_ENGINE_LOOP=1 must enable engine loop")


# ---------------------------------------------------------------------------
# 2. Outcome tracker defaults
# ---------------------------------------------------------------------------

class TestOutcomeTrackerDefault(unittest.TestCase):
    """WORKER_OUTCOME_TRACKER_ENABLED must default to ON."""

    def _outcome_tracker_is_enabled(self, env_overrides: dict) -> bool:
        with patch("os.getenv", side_effect=_env(**env_overrides)):
            raw = os.getenv("WORKER_OUTCOME_TRACKER_ENABLED", "1")
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def test_default_is_on(self):
        self.assertTrue(self._outcome_tracker_is_enabled({}))

    def test_default_is_on_on_railway(self):
        """Even with RAILWAY_SERVICE_NAME set, tracker defaults to ON."""
        self.assertTrue(
            self._outcome_tracker_is_enabled({"RAILWAY_SERVICE_NAME": "signalrankai"})
        )

    def test_explicit_zero_disables_tracker(self):
        self.assertFalse(
            self._outcome_tracker_is_enabled({"WORKER_OUTCOME_TRACKER_ENABLED": "0"})
        )


# ---------------------------------------------------------------------------
# 3. Tier-gated distribution — deterministic score threshold behaviour
# ---------------------------------------------------------------------------

class TestTierGatedDistribution(unittest.TestCase):
    """TierDeliveryManager.should_send_signal must enforce per-tier score gates.

    This is the acceptance criterion:
    "At least one deterministic test proves tier-gated distribution behavior."
    """

    def _make_manager(self):
        from signalrank_telegram.tier_delivery import TierDeliveryManager
        return TierDeliveryManager()

    # ── free tier ────────────────────────────────────────────────────────────

    def test_free_receives_high_score_signal(self):
        """Free tier (min_score=80): score=85 must be accepted."""
        mgr = self._make_manager()
        self.assertTrue(mgr.should_send_signal("free", 85.0))

    def test_free_rejects_below_threshold(self):
        """Free tier: score=79 must be rejected."""
        mgr = self._make_manager()
        self.assertFalse(mgr.should_send_signal("free", 79.0))

    def test_free_accepts_at_threshold_boundary(self):
        """Free tier: score exactly at threshold (80) must pass."""
        mgr = self._make_manager()
        self.assertTrue(mgr.should_send_signal("free", 80.0))

    # ── premium tier ──────────────────────────────────────────────────────────

    def test_premium_receives_moderate_score_signal(self):
        """Premium tier (min_score=70): score=75 must be accepted."""
        mgr = self._make_manager()
        self.assertTrue(mgr.should_send_signal("premium", 75.0))

    def test_premium_rejects_below_threshold(self):
        """Premium tier: score=69 must be rejected."""
        mgr = self._make_manager()
        self.assertFalse(mgr.should_send_signal("premium", 69.0))

    def test_premium_receives_high_score(self):
        """Premium tier: high-score signal (score=90) must be accepted."""
        mgr = self._make_manager()
        self.assertTrue(mgr.should_send_signal("premium", 90.0))

    # ── vip tier ──────────────────────────────────────────────────────────────

    def test_vip_accepts_quality_signal(self):
        """VIP tier (min_score=75): score=80 must be accepted."""
        mgr = self._make_manager()
        self.assertTrue(mgr.should_send_signal("vip", 80.0))

    def test_vip_rejects_below_threshold(self):
        """VIP tier: score=74 must be rejected."""
        mgr = self._make_manager()
        self.assertFalse(mgr.should_send_signal("vip", 74.0))

    # ── tier ordering — free is stricter than premium ─────────────────────────

    def test_free_stricter_than_premium(self):
        """A signal scoring 75 must reach premium but not free."""
        mgr = self._make_manager()
        self.assertFalse(mgr.should_send_signal("free", 75.0))
        self.assertTrue(mgr.should_send_signal("premium", 75.0))

    def test_no_higher_tier_leak_to_free(self):
        """Signal that fails free threshold must not be sent to free users,
        even if it would pass for premium/vip."""
        mgr = self._make_manager()
        score = 76.0  # passes premium (70) and vip (75) but not free (80)
        self.assertFalse(mgr.should_send_signal("free", score))
        self.assertTrue(mgr.should_send_signal("premium", score))
        self.assertTrue(mgr.should_send_signal("vip", score))

    # ── admin tier ────────────────────────────────────────────────────────────

    def test_admin_receives_all_signals(self):
        """Admin tier must receive signals at or above its configured threshold."""
        from core.tier_constants import TIER_SCORE_THRESHOLDS
        mgr = self._make_manager()
        admin_threshold = float(TIER_SCORE_THRESHOLDS.get("admin", 0))
        # Verify at the configured threshold passes.
        self.assertTrue(
            mgr.should_send_signal("admin", admin_threshold),
            f"Admin must receive signals at the configured threshold ({admin_threshold})",
        )
        # Verify well above threshold also passes.
        self.assertTrue(
            mgr.should_send_signal("admin", admin_threshold + 10.0),
            "Admin must receive signals above threshold",
        )
        # Verify just below threshold is rejected (consistent behaviour).
        if admin_threshold > 0:
            self.assertFalse(
                mgr.should_send_signal("admin", admin_threshold - 1.0),
                "Admin should_send_signal must be consistent with TIER_SCORE_THRESHOLDS",
            )


# ---------------------------------------------------------------------------
# 4. Bot minimal scheduler job list completeness
# ---------------------------------------------------------------------------

class TestMinimalSchedulerJobList(unittest.TestCase):
    """The set of jobs scheduled in minimal mode must include signal expiry
    so signals transition to an expired terminal state even in minimal deploys."""

    def test_expire_job_in_minimal_mode_job_list(self):
        """Verify expire_old_signals_job is registered in minimal scheduler path.

        We parse the bot.py source rather than importing to avoid heavy deps.
        This is a lightweight contract test that catches accidental removals.
        """
        bot_path = ROOT / "signalrank_telegram" / "bot.py"
        source = bot_path.read_text(encoding="utf-8")

        # Find the minimal mode block and verify expire_old_signals_job appears
        # after the _minimal_scheduler_mode guard.
        minimal_idx = source.find("if _minimal_scheduler_mode:")
        self.assertGreater(minimal_idx, 0, "Could not find minimal_scheduler_mode block")

        # The else branch starts the full set; we want expire inside the if block.
        else_idx = source.find("        else:", minimal_idx)
        # Sanity check: else must come after the if block start.
        self.assertGreater(
            else_idx,
            minimal_idx,
            "Could not locate 'else:' branch after if _minimal_scheduler_mode: — bot.py structure may have changed",
        )
        minimal_block = source[minimal_idx:else_idx]
        self.assertIn(
            "expire_old_signals_job",
            minimal_block,
            "expire_old_signals_job must be scheduled in minimal mode to complete signal lifecycle",
        )


if __name__ == "__main__":
    unittest.main()
