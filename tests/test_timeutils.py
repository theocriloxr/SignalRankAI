import unittest
from datetime import datetime, timezone

from utils.timeutils import to_naive_utc, to_aware_utc, now_utc_naive


class TimeutilsTest(unittest.TestCase):
    def test_to_naive_aware(self):
        aware = datetime.now(timezone.utc)
        naive = to_naive_utc(aware)
        self.assertIsNotNone(naive)
        self.assertIsNone(naive.tzinfo)

        back = to_aware_utc(naive)
        self.assertIsNotNone(back.tzinfo)
        self.assertEqual(back.tzinfo, timezone.utc)

    def test_now_utc_naive(self):
        n = now_utc_naive()
        self.assertIsNotNone(n)
        self.assertIsNone(n.tzinfo)
        # should be close to actual utc now (allow small drift)
        self.assertAlmostEqual(n.timestamp(), datetime.utcnow().timestamp(), delta=10)


if __name__ == "__main__":
    unittest.main()
