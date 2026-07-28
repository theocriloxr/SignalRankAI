from __future__ import annotations

from engine.adaptive.types import Direction, MarketContext, PriceZone, StrategyEvidence, clamp
from .helpers import atr, fingerprint, ohlcv, targets


class SupplyDemandComponent:
    strategy_id = "adaptive.supply_demand"
    version = "1.0.0"
    family = "supply_demand"

    def evaluate(self, context: MarketContext) -> tuple[StrategyEvidence, ...]:
        candles=context.candles
        if not context.data_quality.usable or len(candles)<30: return ()
        opens, highs, lows, closes, _=ohlcv(candles)
        tr=max(atr(candles), abs(closes[-1])*0.001)
        best=None
        # Search only completed bases and require a strong departure afterwards.
        for i in range(max(2,len(candles)-24), len(candles)-3):
            base_range=highs[i]-lows[i]
            if base_range>tr*0.9: continue
            before=closes[i]-closes[i-2]
            after=closes[i+2]-closes[i]
            if abs(after)<tr*1.2: continue
            kind=("demand" if after>0 else "supply")
            pattern=("drop_base_rally" if before<0 and after>0 else "rally_base_rally" if after>0 else "rally_base_drop" if before>0 else "drop_base_drop")
            touches=sum(1 for j in range(i+3,len(candles)) if lows[j]<=highs[i] and highs[j]>=lows[i])
            freshness=max(0.0,1.0-touches*0.25)
            score=abs(after)/tr*0.2+freshness*0.5
            if best is None or score>best[0]: best=(score,i,kind,pattern,touches,freshness)
        if best is None: return ()
        _,i,kind,pattern,touches,freshness=best
        zone=PriceZone(kind,lows[i],highs[i],"active" if touches<3 else "partially_mitigated",clamp(0.55+freshness*0.3),i,(lows[i]-tr*0.2 if kind=="demand" else highs[i]+tr*0.2))
        price=closes[-1]
        distance=min(abs(price-zone.lower),abs(price-zone.upper))/max(tr,1e-12)
        if distance>1.5: return ()
        direction=Direction.LONG if kind=="demand" else Direction.SHORT
        stop=zone.invalidation
        confidence=clamp((0.64+freshness*0.18-min(0.12,distance*0.05))*context.data_quality.score)
        return (StrategyEvidence(
            strategy_id=self.strategy_id,strategy_version=self.version,family=self.family,asset=context.asset,asset_class=context.asset_class,timeframe=context.timeframe,direction=direction,setup_type=pattern,confidence=confidence,raw_score=confidence*100,zones=(zone,),entry_proposal=price,stop_proposal=stop,target_proposals=targets(price,stop,direction.value),invalidation=f"zone invalidated beyond {stop:.8g}",regime_compatibility=0.8,data_quality=context.data_quality,evidence={"touch_count":touches,"freshness":freshness,"departure_atr":abs(closes[i+2]-closes[i])/tr,"distance_atr":distance},duplicate_fingerprint=fingerprint({"a":context.asset,"tf":context.timeframe,"f":self.family,"i":i,"k":kind}),
        ),)
