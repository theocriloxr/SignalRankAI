from __future__ import annotations

from engine.adaptive.types import Direction, MarketContext, StrategyEvidence, clamp
from .helpers import atr, confirmed_pivots, fingerprint, ohlcv, targets


class ElliottWaveComponent:
    strategy_id="adaptive.elliott";version="1.0.0";family="elliott_wave"
    def evaluate(self, context: MarketContext)->tuple[StrategyEvidence,...]:
        if not context.data_quality.usable or len(context.candles)<70:return ()
        _,_,_,closes,_=ohlcv(context.candles);ph,pl=confirmed_pivots(context.candles,3)
        pts=sorted(ph[-5:]+pl[-5:],key=lambda x:x[0])
        if len(pts)<6:return ()
        vals=[p[1] for p in pts[-6:]]
        bullish=vals[2]>vals[0] and vals[4]>vals[2] and vals[3]>vals[1] and vals[5]>vals[3]
        bearish=vals[2]<vals[0] and vals[4]<vals[2] and vals[3]<vals[1] and vals[5]<vals[3]
        if not bullish and not bearish:return ()
        direction=Direction.LONG if bullish else Direction.SHORT
        setup="probable_impulse_continuation"
        alternatives=["impulse_wave_5","extended_wave_3"] if bullish or bearish else []
        tr=max(atr(context.candles),abs(closes[-1])*0.001);stop=min(vals[-3:])-tr*0.25 if bullish else max(vals[-3:])+tr*0.25
        confidence=clamp(0.61*context.data_quality.score)
        return (StrategyEvidence(strategy_id=self.strategy_id,strategy_version=self.version,family=self.family,asset=context.asset,asset_class=context.asset_class,timeframe=context.timeframe,direction=direction,setup_type=setup,confidence=confidence,raw_score=confidence*100,entry_proposal=closes[-1],stop_proposal=stop,target_proposals=targets(closes[-1],stop,direction.value),invalidation="wave count invalidated by overlap or structural break",regime_compatibility=0.70,data_quality=context.data_quality,evidence={"pivot_values":vals,"preferred_count":alternatives[0],"alternative_counts":alternatives[1:],"probabilistic":True},conflicts=("wave_count_not_unique",),duplicate_fingerprint=fingerprint({"a":context.asset,"tf":context.timeframe,"f":self.family,"v":[round(x,8) for x in vals]})),)
