import unittest

from core.paper_ledger import PaperLedger, PaperPosition


class TestPaperLedgerExits(unittest.IsolatedAsyncioTestCase):
    async def _ledger_with_position(self, position: PaperPosition) -> PaperLedger:
        ledger = PaperLedger()
        ledger._redis = None

        async def _open_positions(_user_id: int):
            return [position]

        ledger.get_open_positions = _open_positions
        return ledger

    async def test_long_stop_loss_hit_below_entry(self):
        pos = PaperPosition(
            {
                "position_id": "p1",
                "user_id": 1,
                "asset": "BTCUSDT",
                "direction": "long",
                "entry_price": 100.0,
                "stop_loss": 95.0,
                "take_profit": 110.0,
                "status": "OPEN",
            }
        )
        ledger = await self._ledger_with_position(pos)
        self.assertEqual(await ledger.check_tp_sl_hit(1, "BTCUSDT", 94.9), "SL")

    async def test_long_take_profit_hit(self):
        pos = PaperPosition(
            {
                "position_id": "p2",
                "user_id": 1,
                "asset": "BTCUSDT",
                "direction": "long",
                "entry_price": 100.0,
                "stop_loss": 95.0,
                "take_profit": '[{"price": 110.0}]',
                "status": "OPEN",
            }
        )
        ledger = await self._ledger_with_position(pos)
        self.assertEqual(await ledger.check_tp_sl_hit(1, "BTCUSDT", 110.1), "TP")

    async def test_short_stop_loss_hit_above_entry(self):
        pos = PaperPosition(
            {
                "position_id": "p3",
                "user_id": 1,
                "asset": "ETHUSDT",
                "direction": "short",
                "entry_price": 100.0,
                "stop_loss": 105.0,
                "take_profit": 90.0,
                "status": "OPEN",
            }
        )
        ledger = await self._ledger_with_position(pos)
        self.assertEqual(await ledger.check_tp_sl_hit(1, "ETHUSDT", 105.1), "SL")

    async def test_short_take_profit_hit(self):
        pos = PaperPosition(
            {
                "position_id": "p4",
                "user_id": 1,
                "asset": "ETHUSDT",
                "direction": "short",
                "entry_price": 100.0,
                "stop_loss": 105.0,
                "take_profit": [{"target": 90.0}],
                "status": "OPEN",
            }
        )
        ledger = await self._ledger_with_position(pos)
        self.assertEqual(await ledger.check_tp_sl_hit(1, "ETHUSDT", 89.9), "TP")


if __name__ == "__main__":
    unittest.main()
