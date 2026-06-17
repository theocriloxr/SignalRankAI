from data.alternative_providers import _context_from_payload, fetch_onchain_context
from engine.onchain_alpha import OnChainAlpha
from ml.features import extract_features


def test_onchain_payload_normalization():
    payload = {
        "data": {
            "exchange_net_flow": 12.5,
            "liquidation_heatmap_score": 0.87,
            "liquidation_heatmap_density": 0.31,
        }
    }

    context = _context_from_payload(payload, "glassnode")

    assert context["onchain_source"] == "glassnode"
    assert float(context["exchange_net_flow"]) == 12.5
    assert float(context["liquidation_heatmap_score"]) == 0.87
    assert float(context["liquidation_heatmap_density"]) == 0.31


def test_fetch_onchain_context_fails_open_without_endpoints():
    context = __import__("asyncio").run(fetch_onchain_context("BTCUSDT"))

    assert context["onchain_source"] in {"none", "glassnode", "cryptoquant"}
    assert float(context["exchange_net_flow"]) == 0.0


def test_extract_features_includes_onchain_fields():
    signal = {"asset": "BTCUSDT", "timeframe": "5m", "strategy": "EMA Trend"}
    market_data = {
        "5m": {"candles": [{"open": 99, "high": 101, "low": 98, "close": 100, "volume": 1}]},
        "_macro": {
            "exchange_net_flow": 4.2,
            "exchange_inflow": 6.0,
            "exchange_outflow": 1.8,
            "liquidation_heatmap_score": 0.9,
            "liquidation_heatmap_density": 0.4,
            "onchain_source": "glassnode",
        },
    }

    features = extract_features(signal, market_data)

    assert float(features["exchange_net_flow"]) == 4.2
    assert float(features["liquidation_heatmap_score"]) == 0.9
    assert float(features["onchain_source_flag"]) == 1.0


def test_onchain_alpha_vetoes_long_on_exchange_inflow_spike(monkeypatch):
    async def fake_context(symbol):
        return {
            "onchain_source": "glassnode",
            "exchange_net_flow": 10.0,
            "exchange_inflow": 25.0,
            "exchange_outflow": 2.0,
            "liquidation_heatmap_score": 0.0,
            "liquidation_heatmap_density": 0.0,
        }

    import data.alternative_providers as providers

    monkeypatch.setattr(providers, "fetch_onchain_context", fake_context)

    alpha = OnChainAlpha()
    should_veto, reason = __import__("asyncio").run(
        alpha._check_exchange_inflows("BTC", "long")
    )

    assert should_veto is True
    assert "exchange_inflow_spike" in reason
