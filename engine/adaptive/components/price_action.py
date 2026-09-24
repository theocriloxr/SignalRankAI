from __future__ import annotations

from core.candle_evidence import build_candle_intelligence
from engine.adaptive.types import Direction, MarketContext, StrategyEvidence, clamp
from .helpers import atr, confirmed_pivots, fingerprint, ohlcv, targets


class PriceActionComponent:
    strategy_id = "adaptive.price_action"
    version = "2.0.0"
    family = "price_action"

    def evaluate(self, context: MarketContext) -> tuple[StrategyEvidence, ...]:
        candles = context.candles
        if not context.data_quality.usable or len(candles) < 25:
            return ()
        opens, highs, lows, closes, volumes = ohlcv(candles)
        o1, h1, l1, c1 = opens[-1], highs[-1], lows[-1], closes[-1]
        o0, h0, l0, c0 = opens[-2], highs[-2], lows[-2], closes[-2]
        body = abs(c1-o1); rng = max(h1-l1, 1e-12)
        bullish_engulf = c1 > o1 and c0 < o0 and c1 >= o0 and o1 <= c0
        bearish_engulf = c1 < o1 and c0 > o0 and o1 >= c0 and c1 <= o0
        pin_bull = (min(o1,c1)-l1) >= max(body*2.0, rng*0.45) and (h1-max(o1,c1)) <= rng*0.25
        pin_bear = (h1-max(o1,c1)) >= max(body*2.0, rng*0.45) and (min(o1,c1)-l1) <= rng*0.25
        inside = h1 < h0 and l1 > l0
        outside = h1 > h0 and l1 < l0
        ph, pl = confirmed_pivots(candles, 2)
        recent_high = max((x[1] for x in ph[-3:]), default=h0)
        recent_low = min((x[1] for x in pl[-3:]), default=l0)
        breakout_long = c1 > recent_high and c0 <= recent_high
        breakout_short = c1 < recent_low and c0 >= recent_low
        long_intelligence = build_candle_intelligence(
            candles,
            direction="LONG",
            timeframe=context.timeframe,
        )
        short_intelligence = build_candle_intelligence(
            candles,
            direction="SHORT",
            timeframe=context.timeframe,
        )
        confirmed_long = (
            long_intelligence["selected_focus"] == "previous_confirmed"
            and long_intelligence["alignment"] == "supportive"
            and (
                long_intelligence["rejection"] == "lower_price_rejection"
                or long_intelligence["breakout"] == "bullish_breakout"
            )
        )
        confirmed_short = (
            short_intelligence["selected_focus"] == "previous_confirmed"
            and short_intelligence["alignment"] == "supportive"
            and (
                short_intelligence["rejection"] == "higher_price_rejection"
                or short_intelligence["breakout"] == "bearish_breakdown"
            )
        )
        direction = Direction.NEUTRAL; setup = ""; base = 0.0
        if confirmed_long and not confirmed_short:
            direction = Direction.LONG
            setup = "confirmed_bullish_price_action"
            base = 0.74
            stop = min(l1, recent_low) - atr(candles)*0.10
        elif confirmed_short and not confirmed_long:
            direction = Direction.SHORT
            setup = "confirmed_bearish_price_action"
            base = 0.74
            stop = max(h1, recent_high) + atr(candles)*0.10
        elif bullish_engulf or pin_bull or breakout_long:
            direction = Direction.LONG
            setup = "bullish_engulfing" if bullish_engulf else ("bullish_rejection" if pin_bull else "breakout_close")
            # A last-candle pattern is evidence awaiting follow-through, so it
            # starts below a fully confirmed setup.
            base = 0.60 + (0.08 if breakout_long else 0.0)
            stop = min(l1, recent_low) - atr(candles)*0.10
        elif bearish_engulf or pin_bear or breakout_short:
            direction = Direction.SHORT
            setup = "bearish_engulfing" if bearish_engulf else ("bearish_rejection" if pin_bear else "breakdown_close")
            base = 0.60 + (0.08 if breakout_short else 0.0)
            stop = max(h1, recent_high) + atr(candles)*0.10
        else:
            return ()
        intelligence = long_intelligence if direction is Direction.LONG else short_intelligence
        volume_confirmation = intelligence.get("volume_confirmation")
        if volume_confirmation is None:
            volume_confirmation = bool(len(volumes) >= 21 and volumes[-1] > (sum(volumes[-21:-1])/20.0)*1.15)
        confidence = clamp((base + (0.05 if volume_confirmation else 0.0)) * context.data_quality.score)
        return (StrategyEvidence(
            strategy_id=self.strategy_id, strategy_version=self.version, family=self.family,
            asset=context.asset, asset_class=context.asset_class, timeframe=context.timeframe,
            direction=direction, setup_type=setup, confidence=confidence, raw_score=confidence*100,
            entry_proposal=c1, stop_proposal=stop, target_proposals=targets(c1, stop, direction.value),
            invalidation=f"close beyond {stop:.8g}", regime_compatibility=0.85, data_quality=context.data_quality,
            evidence={
                "bullish_engulf": bullish_engulf,
                "bearish_engulf": bearish_engulf,
                "pin_bull": pin_bull,
                "pin_bear": pin_bear,
                "inside_bar": inside,
                "outside_bar": outside,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "volume_confirmation": volume_confirmation,
                "candle_intelligence": intelligence,
                "rejection_is_evidence_not_proof": True,
            },
            duplicate_fingerprint=fingerprint({"a":context.asset,"tf":context.timeframe,"f":self.family,"s":setup,"e":round(c1,8)}),
        ),)
