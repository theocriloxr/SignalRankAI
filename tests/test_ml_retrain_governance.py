import unittest
from unittest.mock import AsyncMock, patch


class TestMLRetrainGovernance(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_retrain_delegates_to_governed_trainer(self):
        from ml.retrain import retrain_model

        governed = AsyncMock(return_value=True)
        with patch("ml.train_model.main", governed):
            result = await retrain_model()

        self.assertTrue(result)
        governed.assert_awaited_once_with()

    async def test_governed_trainer_failure_preserves_current_model(self):
        from ml.retrain import retrain_model

        governed = AsyncMock(side_effect=RuntimeError("training blocked"))
        with patch("ml.train_model.main", governed):
            result = await retrain_model()

        self.assertFalse(result)
        governed.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
