from __future__ import annotations

from engine.adaptive.types import Direction, MarketContext, StrategyEvidence, clamp
from .helpers import atr, fingerprint, ohlcv, targets


class WyckoffComponent:
    strategy_id="adaptive.wyckoff";version="1.0.0";family="wyckoff"
    def evaluate(self, context: MarketContext)->tuple[StrategyEvidence,...]:
        if not context.data_quality.usable or len(context.candles)<60:return ()
        _,highs,lows,closes,volumes=ohlcv(context.candles);window=closes[-40:];tr=max(atr(context.candles),abs(closes[-1])*0.001)
        range_width=(max(window)-min(window))/max(abs(sum(window)/len(window)),1e-9)
        if range_width>0.12:return ()
        vavg=sum(volumes[-40:-5])/max(1,len(volumes[-40:-5]));recent_v=sum(volumes[-5:])/5 if len(volumes)>=5 else 0
        spring=lows[-1]<min(lows[-20:-1]) and closes[-1]>min(closes[-20:-1])
        upthrust=highs[-1]>max(highs[-20:-1]) and closes[-1]<max(closes[-20:-1])
        if spring:direction=Direction.LONG;setup="spring_phase_c";stop=lows[-1]-tr*0.2
        elif upthrust:direction=Direction.SHORT;setup="upthrust_phase_c";stop=highs[-1]+tr*0.2
        else:return ()
        confidence=clamp((0.61+(0.07 if recent_v>vavg*1.2 else 0))*context.data_quality.score)
        return (StrategyEvidence(strategy_id=self.strategy_id,strategy_version=self.version,family=self.family,asset=context.asset,asset_class=context.asset_class,timeframe=context.timeframe,direction=direction,setup_type=setup,confidence=confidence,raw_score=confidence*100,entry_proposal=closes[-1],stop_proposal=stop,target_proposals=targets(closes[-1],stop,direction.value),invalidation=f"range extreme invalidated beyond {stop:.8g}",regime_compatibility=0.82,data_quality=context.data_quality,evidence={"range_width":range_width,"recent_volume_ratio":recent_v/max(vavg,1e-9),"classification_uncertain":True,"forced_schematic":False},conflicts=("incomplete_wyckoff_schematic",),duplicate_fingerprint=fingerprint({"a":context.asset,"tf":context.timeframe,"f":self.family,"s":setup,"e":round(closes[-1],8)})),)
