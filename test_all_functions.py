import unittest
import types
import engine.signal_controller as signal_controller
import engine.scoring as scoring
import engine.risk as risk
import engine.regime as regime
import engine.ranking as ranking
import engine.ml as ml
import engine.core as core
import engine.consensus as consensus
import paystack.paystack as paystack
import strategies.volatility as volatility
import strategies.trend as trend
import strategies.structure as structure
import strategies.momentum as momentum
from db.pg_compat import postgres_enabled, get_all_user_ids_compat

class TestAllFunctions(unittest.TestCase):
    def test_signal_controller_functions(self):
        ctrl = signal_controller.SignalController()
        self.assertIsInstance(ctrl.is_kill_switch_enabled(), bool)
        ctrl.enable_kill_switch("test", admin_id=1)
        self.assertTrue(ctrl.is_kill_switch_enabled())
        ctrl.disable_kill_switch(admin_id=1)
        self.assertFalse(ctrl.is_kill_switch_enabled())
        ctrl.log_audit_event("test_event", user_id=1, details={"foo": "bar"})
        self.assertIsInstance(ctrl.deduplicate_signals([]), list)
        self.assertIsInstance(ctrl.cap_correlation([]), list)
        self.assertIsInstance(ctrl.rank_and_release([]), dict)
        self.assertIsInstance(ctrl.is_drawdown(), bool)
        self.assertIsInstance(ctrl.generate_watermark({"asset": "BTC"}), str)
        self.assertTrue(ctrl.session_active({}))
        self.assertIsInstance(ctrl.approve_signals([], None), list)

    def test_scoring_functions(self):
        dummy = {"asset": "BTC"}
        self.assertIsInstance(scoring.calculate_signal_score(dummy, None, None), (int, float))
        self.assertIsInstance(scoring.strategy_agreement_score(dummy), float)
        self.assertIsInstance(scoring.rr_score(1.0), float)
        self.assertIsInstance(scoring.htf_alignment_score(dummy), float)
        self.assertIsInstance(scoring.regime_fit_score(dummy, None), float)
        self.assertIsInstance(scoring.volatility_quality_score(dummy), float)
        self.assertIsInstance(scoring.historical_winrate_score(dummy), float)
        self.assertIsInstance(scoring.liquidity_score(dummy), float)

    def test_risk_functions(self):
        dummy = {"asset": "BTC"}
        self.assertIsInstance(risk.calculate_dynamic_risk(dummy, None), dict)
        self.assertIsInstance(risk.calculate_position_size(dummy, {"risk": 1}), (int, float))

    def test_regime_function(self):
        dummy_market_data = {'4h': {'indicators': {'adx': 10, 'atr': 1, 'bollinger': {'width': 0.1}}}}
        self.assertIsInstance(regime.detect_market_regime(dummy_market_data), str)

    def test_ranking_function(self):
        self.assertIsInstance(ranking.rank_signals([]), dict)

    def test_ml_functions(self):
        self.assertIsNone(ml.adjust_weight_based_on_performance(None))
        self.assertIsInstance(ml.disable_strategies_with_drawdown(), list)
        self.assertIsInstance(ml.weekly_job(), bool)

    def test_core_functions(self):
        self.assertIsInstance(core.load_tradable_assets(), list)
        # main_loop expects to call rank_signals with signals; skip or mock for now
        # self.assertIsNone(core.main_loop())

    def test_consensus_functions(self):
        self.assertIsInstance(consensus.apply_consensus_filter([]), list)
        self.assertIsInstance(consensus.group_by_asset_and_direction([]), dict)
        self.assertIsInstance(consensus.unique_strategy_groups([]), set)
        self.assertIsInstance(consensus.contains_required_groups([]), bool)
        self.assertIsNone(consensus.best_signal_in_group([]))
        self.assertIsInstance(consensus.best_signal_in_group([{'foo': 'bar'}]), dict)

    def test_database_functions(self):
        # Postgres-only: ensure compat layer fails closed when DATABASE_URL is missing,
        # and is callable when Postgres is configured.
        if postgres_enabled():
            ids = get_all_user_ids_compat()
            self.assertIsInstance(ids, list)
        else:
            with self.assertRaises(Exception):
                _ = get_all_user_ids_compat()

    def test_paystack_functions(self):
        self.assertIsInstance(paystack.match_amount_to_tier(10000), (str, type(None)))
        self.assertIsInstance(paystack.verify_webhook_signature(b"body", "sig"), bool)
        self.assertIsInstance(paystack.generate_paystack_link(1, 1000, extra_count=1), str)
        # verify_payment is not tested here due to external dependency

    def test_strategy_functions(self):
        dummy_data = {
            'indicators': {
                'atr': 2,
                'bollinger': {'width': 1},
                'ema_fast': 2,
                'ema_slow': 1.5,
                'ema_trend': 1,
                'rsi': 50
            },
            'candles': [{'close': 100, 'low': 90}]
        }
        self.assertIsInstance(volatility.volatility_strategies("BTC", "1h", dummy_data), list)
        self.assertIsInstance(trend.trend_strategies("BTC", "1h", dummy_data), list)
        self.assertIsInstance(structure.structure_strategy("BTC", "1h", dummy_data), list)
        self.assertIsInstance(momentum.momentum_strategies("BTC", "1h", dummy_data), list)

if __name__ == "__main__":
    unittest.main()
