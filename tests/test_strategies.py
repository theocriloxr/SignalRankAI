import unittest

from engine.strategies.commodity import CommodityStrategy


class TestCommodityStrategy(unittest.TestCase):
    def test_generate_no_data(self):
        s = CommodityStrategy()
        out = s.generate({})
        self.assertEqual(out, [])

    def test_generate_simple_long(self):
        s = CommodityStrategy()
        market = {
            "1h": {
                "candles": [
                    {"timestamp": 1, "close": 100},
                    {"timestamp": 2, "close": 102},
                ],
                "asset": "XAUUSD",
            }
        }
        out = s.generate(market)
        self.assertTrue(len(out) >= 1)
        sig = out[0]
        self.assertEqual(sig.direction, "long")


if __name__ == "__main__":
    unittest.main()
