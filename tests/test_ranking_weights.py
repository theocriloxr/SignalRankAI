import unittest
from unittest.mock import patch

from engine import ml
from engine.ranking import rank_signals


class TestRankingWeights(unittest.TestCase):
    def setUp(self):
        ml._STRATEGY_WEIGHT_CACHE["weights"] = {}
        ml._STRATEGY_WEIGHT_CACHE["updated_at"] = None

    def test_rank_signals_uses_live_strategy_weight(self):
        ml._STRATEGY_WEIGHT_CACHE.setdefault("weights", {})["ema crossover"] = {"weight": 1.5, "updated_at": "now"}

        with patch("engine.ranking.score_signal", return_value=None):
            ranked = rank_signals([
                {
                    "asset": "BTCUSDT",
                    "timeframe": "1h",
                    "strategy_name": "EMA Crossover",
                    "score": 70,
                    "direction": "long",
                }
            ])

        self.assertEqual(len(ranked["vip"]), 1)
        self.assertAlmostEqual(ranked["vip"][0]["strategy_weight"], 1.5)
        self.assertGreater(ranked["vip"][0]["score_final"], 80)


if __name__ == "__main__":
    unittest.main()