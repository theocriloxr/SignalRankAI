from typing import Protocol, List, Dict, Any


class Connector(Protocol):
    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:  # pragma: no cover - interface
        """Return a list of candle dicts with keys: time, open, high, low, close, volume."""
        ...
