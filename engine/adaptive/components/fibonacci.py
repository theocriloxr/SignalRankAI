from __future__ import annotations

from engine.adaptive.types import Direction, MarketContext, PriceZone, StrategyEvidence, clamp
from .helpers import atr, confirmed_pivots, fingerprint, ohlcv, targets


class FibonacciComponent:
    strategy_id="adaptive.fibonacci"; version="1.0.0"; family="fibonacci"
    def evaluate(self, context: MarketContext) -> tuple[StrategyEvidence,...]:
        if not context.data_quality.usable or len(context.candles)<35: return ()
        _,highs,lows,closes,_=ohlcv(context.candles); ph,pl=confirmed_pivots(context.candles,2)
        if not ph or not pl: return ()
        hi_i,hi=ph[-1]; lo_i,lo=pl[-1]
        if hi==lo: return ()
        bullish=lo_i<hi_i
        span=abs(hi-lo)
        if bullish:
            z1,z2=hi-span*0.786,hi-span*0.618; direction=Direction.LONG; stop=lo-atr(context.candles)*0.15
        else:
            z1,z2=lo+span*0.618,lo+span*0.786; direction=Direction.SHORT; stop=hi+atr(context.candles)*0.15
        lower,upper=min(z1,z2),max(z1,z2); price=closes[-1]
        tolerance=max(atr(context.candles)*0.25,abs(price)*0.001)
        if not lower-tolerance<=price<=upper+tolerance: return ()
        zone=PriceZone("golden_pocket",lower,upper,"active",0.72,min(hi_i,lo_i),stop)
        confidence=clamp(0.72*context.data_quality.score)
        return (StrategyEvidence(strategy_id=self.strategy_id,strategy_version=self.version,family=self.family,asset=context.asset,asset_class=context.asset_class,timeframe=context.timeframe,direction=direction,setup_type="confirmed_swing_golden_pocket",confidence=confidence,raw_score=confidence*100,zones=(zone,),entry_proposal=price,stop_proposal=stop,target_proposals=targets(price,stop,direction.value),invalidation=f"anchor invalidated beyond {stop:.8g}",regime_compatibility=0.82,data_quality=context.data_quality,evidence={"swing_high":hi,"swing_low":lo,"high_index":hi_i,"low_index":lo_i,"fib_618":z1,"fib_786":z2},duplicate_fingerprint=fingerprint({"a":context.asset,"tf":context.timeframe,"f":self.family,"hi":round(hi,8),"lo":round(lo,8)})),)
