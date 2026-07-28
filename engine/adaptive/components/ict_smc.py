from __future__ import annotations

from engine.adaptive.types import Direction, MarketContext, PriceZone, StrategyEvidence, clamp
from .helpers import atr, confirmed_pivots, fingerprint, ohlcv, targets


class ICTSmartMoneyComponent:
    strategy_id = "adaptive.ict_smc"
    version = "1.0.0"
    family = "ict_smc"

    def evaluate(self, context: MarketContext) -> tuple[StrategyEvidence, ...]:
        candles = context.candles
        if not context.data_quality.usable or len(candles) < 35:
            return ()
        opens, highs, lows, closes, _ = ohlcv(candles)
        ph, pl = confirmed_pivots(candles, 2)
        if not ph or not pl:
            return ()
        last = len(candles) - 1
        last_close, last_high, last_low = closes[-1], highs[-1], lows[-1]
        prior_high = ph[-1][1]
        prior_low = pl[-1][1]
        tr = max(atr(candles), abs(last_close) * 0.001)
        displacement = abs(closes[-1] - opens[-1]) / tr
        swept_high = last_high > prior_high and last_close < prior_high
        swept_low = last_low < prior_low and last_close > prior_low
        bos_long = last_close > prior_high and displacement >= 0.8
        bos_short = last_close < prior_low and displacement >= 0.8
        direction = Direction.NEUTRAL
        setup = "structure_observation"
        entry = stop = None
        confidence = 0.0
        zones: list[PriceZone] = []
        if swept_low or bos_long:
            direction, setup = Direction.LONG, ("sell_side_liquidity_sweep" if swept_low else "bullish_break_of_structure")
            entry = last_close
            stop = min(last_low, prior_low) - tr * 0.15
            confidence = 0.68 + min(0.16, displacement * 0.06)
        elif swept_high or bos_short:
            direction, setup = Direction.SHORT, ("buy_side_liquidity_sweep" if swept_high else "bearish_break_of_structure")
            entry = last_close
            stop = max(last_high, prior_high) + tr * 0.15
            confidence = 0.68 + min(0.16, displacement * 0.06)
        else:
            return ()
        # Three-candle imbalance; only completed historical candles are used.
        if len(candles) >= 4:
            left_high, left_low = highs[-4], lows[-4]
            right_high, right_low = highs[-2], lows[-2]
            if right_low > left_high:
                zones.append(PriceZone("bullish_fvg", left_high, right_low, confidence=0.65, created_index=last-2, invalidation=left_low))
            if right_high < left_low:
                zones.append(PriceZone("bearish_fvg", right_high, left_low, confidence=0.65, created_index=last-2, invalidation=left_high))
        score = clamp(confidence * context.data_quality.score)
        return (StrategyEvidence(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            family=self.family,
            asset=context.asset,
            asset_class=context.asset_class,
            timeframe=context.timeframe,
            direction=direction,
            setup_type=setup,
            confidence=score,
            raw_score=score * 100,
            zones=tuple(zones),
            entry_proposal=entry,
            stop_proposal=stop,
            target_proposals=targets(entry, stop, direction.value) if entry is not None and stop is not None else (),
            invalidation=f"close beyond {stop:.8g}" if stop is not None else None,
            regime_compatibility=0.9 if str(context.regime).upper() in {"TRENDING", "VOLATILE", "BREAKOUT"} else 0.65,
            data_quality=context.data_quality,
            evidence={"prior_swing_high": prior_high, "prior_swing_low": prior_low, "displacement_atr": displacement, "swept_high": swept_high, "swept_low": swept_low, "bos_long": bos_long, "bos_short": bos_short},
            duplicate_fingerprint=fingerprint({"a": context.asset, "tf": context.timeframe, "family": self.family, "setup": setup, "ph": round(prior_high, 8), "pl": round(prior_low, 8)}),
        ),)
