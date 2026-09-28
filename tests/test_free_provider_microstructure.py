import pytest


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def json(self):
        return self._payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.closed = False

    def get(self, *_args, **_kwargs):
        return _Response(self.payload)


@pytest.mark.asyncio
async def test_order_book_normalizes_bybit_public_payload(monkeypatch):
    from engine.microstructure import OrderBookAnalyzer

    analyzer = OrderBookAnalyzer()
    session = _Session({"result": {"b": [["100", "2"]], "a": [["101", "3"]]}})

    async def _session():
        return session

    monkeypatch.setenv("CRYPTO_MICROSTRUCTURE_PROVIDERS", "bybit")
    monkeypatch.setattr(analyzer, "_get_session", _session)

    result = await analyzer.fetch_order_book("BTCUSDT")

    assert result["provider"] == "bybit"
    assert result["bids"] == [["100", "2"]]
    assert result["asks"] == [["101", "3"]]


@pytest.mark.asyncio
async def test_funding_rate_uses_bybit_without_api_key(monkeypatch):
    from engine.derivatives import SqueezeDetector

    detector = SqueezeDetector()
    session = _Session({"result": {"list": [{"fundingRate": "0.00025"}]}})

    async def _session():
        return session

    monkeypatch.setenv("CRYPTO_DERIVATIVES_PROVIDERS", "bybit")
    monkeypatch.setattr(detector, "_get_session", _session)

    assert await detector.get_funding_rate("BTCUSDT") == pytest.approx(0.00025)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("funding_rate", "expected"),
    [
        (0.0006, "BEARISH"),
        (-0.0006, "BULLISH"),
        (0.0001, "NEUTRAL"),
        (None, "NEUTRAL"),
    ],
)
async def test_squeeze_bias_uses_valid_public_funding_rate(monkeypatch, funding_rate, expected):
    from engine.derivatives import SqueezeDetector

    detector = SqueezeDetector(extreme_funding_threshold=0.0005)

    async def _funding(_asset):
        return funding_rate

    monkeypatch.setattr(detector, "get_funding_rate", _funding)

    assert await detector.get_squeeze_bias("BTCUSDT") == expected


@pytest.mark.asyncio
async def test_squeeze_veto_blocks_only_direction_exposed_to_crowded_side(monkeypatch):
    from engine.derivatives import SqueezeDetector

    detector = SqueezeDetector(extreme_funding_threshold=0.0005)

    async def _funding(_asset):
        return 0.0007

    monkeypatch.setattr(detector, "get_funding_rate", _funding)

    assert await detector.check_veto("BTCUSDT", "LONG") == (
        True,
        "veto_long_squeeze_bias_BEARISH",
    )
    assert await detector.check_veto("BTCUSDT", "SHORT") == (False, "ok")
