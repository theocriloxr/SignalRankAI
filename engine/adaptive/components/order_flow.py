from __future__ import annotations

from engine.adaptive.types import Direction, EvidenceQuality, MarketContext, StrategyEvidence, clamp
from .helpers import atr, fingerprint, ohlcv, targets


class OrderFlowComponent:
    strategy_id="adaptive.order_flow";version="1.0.0";family="order_flow"
    def evaluate(self, context: MarketContext)->tuple[StrategyEvidence,...]:
        if not context.data_quality.usable or len(context.candles)<25:return ()
        _,_,_,closes,_=ohlcv(context.candles)
        genuine=[]
        for c in context.candles[-20:]:
            bid=c.get("bid_volume");ask=c.get("ask_volume")
            if bid is not None and ask is not None:
                try:genuine.append(float(ask)-float(bid))
                except (TypeError,ValueError):pass
            elif c.get("delta") is not None:
                try:genuine.append(float(c.get("delta")))
                except (TypeError,ValueError):pass
        if len(genuine)<5:
            # Explicitly return unavailable evidence rather than fabricating delta from candle volume.
            return (StrategyEvidence(strategy_id=self.strategy_id,strategy_version=self.version,family=self.family,asset=context.asset,asset_class=context.asset_class,timeframe=context.timeframe,direction=Direction.NEUTRAL,setup_type="order_flow_unavailable",confidence=0.0,raw_score=0.0,data_quality=context.data_quality,evidence={"reason":"genuine_bid_ask_or_delta_not_available","candle_volume_not_used_as_order_flow":True},evidence_quality=EvidenceQuality.UNAVAILABLE,duplicate_fingerprint=fingerprint({"a":context.asset,"tf":context.timeframe,"f":self.family,"u":True})),)
        cumulative=sum(genuine);magnitude=abs(cumulative)/(sum(abs(x) for x in genuine)+1e-9)
        if magnitude<0.18:return ()
        direction=Direction.LONG if cumulative>0 else Direction.SHORT;tr=max(atr(context.candles),abs(closes[-1])*0.001);stop=closes[-1]-tr*1.2 if direction is Direction.LONG else closes[-1]+tr*1.2
        confidence=clamp((0.60+magnitude*0.25)*context.data_quality.score)
        return (StrategyEvidence(strategy_id=self.strategy_id,strategy_version=self.version,family=self.family,asset=context.asset,asset_class=context.asset_class,timeframe=context.timeframe,direction=direction,setup_type="cumulative_delta_imbalance",confidence=confidence,raw_score=confidence*100,entry_proposal=closes[-1],stop_proposal=stop,target_proposals=targets(closes[-1],stop,direction.value),invalidation="delta imbalance reversal",regime_compatibility=0.78,data_quality=context.data_quality,evidence={"cumulative_delta":cumulative,"normalised_imbalance":magnitude,"samples":len(genuine)},evidence_quality=EvidenceQuality.GENUINE,duplicate_fingerprint=fingerprint({"a":context.asset,"tf":context.timeframe,"f":self.family,"d":round(cumulative,4)})),)
