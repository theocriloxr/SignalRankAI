from __future__ import annotations

from typing import List

from .base import Strategy
from engine.signal import Signal


class CommodityStrategy(Strategy):
    name = "commodity_simple"

    def generate(self, market_data: dict) -> List[Signal]:
        """Simple momentum strategy for commodities as placeholder.

        Expects market_data to contain `timeframes` -> candle lists and `indicators`.
        """
        out: List[Signal] = []
        # Very simple rule: if last close > previous close by X%, create a long signal
        for tf, payload in (market_data or {}).items():
            candles = payload.get("candles") or []
            if len(candles) < 2:
                continue
            last = candles[-1]
            prev = candles[-2]
            try:
                last_close = float(last.get("close"))
                prev_close = float(prev.get("close"))
            except Exception:
                continue
            if prev_close <= 0:
                continue
            pct = (last_close - prev_close) / prev_close
            if pct > 0.01:
                s = Signal(
                    signal_id=f"sim-{tf}-{int(last.get('timestamp', 0))}",
                    asset=payload.get("asset") or "COMMOD",
                    timeframe=tf,
                    direction="long",
                    entry=last_close,
                    stop_loss=prev_close,
                    take_profit=None,
                    score=pct * 100,
                    strategy=self.name,
                    metadata={"pct_move": pct},
                )
                out.append(s)
        return out
