import asyncio
import unittest

from engine.signal_deduplicator import SignalDeduplicator


class TestSignalDeduplicator(unittest.TestCase):
    def setUp(self):
        self.dedup = SignalDeduplicator()

    def test_semantic_similarity_matches_nearby_entry_same_direction(self):
        left = {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
        }
        right = {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "direction": "long",
            "entry": 50005.0,
            "stop_loss": 49005.0,
            "take_profit": 52005.0,
        }

        score = self.dedup._signal_similarity(left, right)

        self.assertGreater(score, 0.9)

    def test_semantic_similarity_rejects_opposite_direction(self):
        left = {"asset": "BTCUSDT", "timeframe": "1h", "direction": "long", "entry": 50000.0}
        right = {"asset": "BTCUSDT", "timeframe": "1h", "direction": "short", "entry": 50000.0}

        score = self.dedup._signal_similarity(left, right)

        self.assertEqual(score, 0.0)

    def test_dedupe_batch_keeps_best_representative(self):
        signals = [
            {
                "asset": "BTCUSDT",
                "timeframe": "1h",
                "direction": "long",
                "entry": 50000.0,
                "stop_loss": 49000.0,
                "take_profit": 52000.0,
                "score": 72,
            },
            {
                "asset": "BTCUSDT",
                "timeframe": "1h",
                "direction": "long",
                "entry": 50060.0,
                "stop_loss": 49060.0,
                "take_profit": 52060.0,
                "score": 85,
            },
            {
                "asset": "ETHUSDT",
                "timeframe": "1h",
                "direction": "long",
                "entry": 3000.0,
                "stop_loss": 2950.0,
                "take_profit": 3100.0,
                "score": 65,
            },
        ]

        deduped = asyncio.run(self.dedup.dedupe_batch(signals))

        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["score"], 85)
        self.assertEqual(deduped[1]["asset"], "ETHUSDT")


if __name__ == "__main__":
    unittest.main()