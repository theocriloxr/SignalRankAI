from __future__ import annotations

from engine.adaptive.types import Direction, MarketContext, PriceZone, StrategyEvidence, clamp
from .helpers import atr, confirmed_pivots, fingerprint, ohlcv, targets

_PATTERNS={
 "gartley":((0.55,0.70),(0.35,0.90),(1.20,1.70),(0.72,0.84)),
 "bat":((0.35,0.55),(0.35,0.90),(1.55,2.70),(0.82,0.93)),
 "butterfly":((0.72,0.84),(0.35,0.90),(1.55,2.70),(1.20,1.35)),
 "crab":((0.35,0.70),(0.35,0.90),(2.20,3.80),(1.50,1.75)),
 "cypher":((0.35,0.65),(1.10,1.60),(0.70,0.82),(0.70,0.82)),
}

class HarmonicComponent:
    strategy_id="adaptive.harmonic"; version="1.0.0"; family="harmonic"
    def evaluate(self, context: MarketContext) -> tuple[StrategyEvidence,...]:
        if not context.data_quality.usable or len(context.candles)<60:return ()
        _,_,_,closes,_=ohlcv(context.candles); ph,pl=confirmed_pivots(context.candles,2)
        points=sorted(ph[-4:]+pl[-4:],key=lambda x:x[0])
        # retain alternating extrema only
        alt=[]
        for idx,val in points:
            kind="H" if (idx,val) in ph else "L"
            if alt and alt[-1][2]==kind:
                if (kind=="H" and val>alt[-1][1]) or (kind=="L" and val<alt[-1][1]):alt[-1]=(idx,val,kind)
            else: alt.append((idx,val,kind))
        if len(alt)<5:return ()
        x,a,b,c,d=alt[-5:]; xa=abs(a[1]-x[1]); ab=abs(b[1]-a[1]); bc=abs(c[1]-b[1]); cd=abs(d[1]-c[1]); xd=abs(d[1]-x[1])
        if min(xa,ab,bc)<=0:return ()
        ratios=(ab/xa,bc/ab,cd/bc,xd/xa)
        matched=None; error=999.0
        for name,bounds in _PATTERNS.items():
            errs=[]; ok=True
            for value,(lo,hi) in zip(ratios,bounds):
                if not lo<=value<=hi:ok=False;break
                errs.append(abs(value-(lo+hi)/2)/max((hi-lo)/2,1e-9))
            if ok and sum(errs)<error:matched=name;error=sum(errs)
        # AB=CD fallback
        if matched is None and 0.85<=cd/ab<=1.15: matched="abcd";error=abs(cd/ab-1)
        if matched is None:return ()
        direction=Direction.LONG if d[2]=="L" else Direction.SHORT; tr=max(atr(context.candles),abs(closes[-1])*0.001)
        stop=d[1]-tr*0.5 if direction is Direction.LONG else d[1]+tr*0.5
        prz=PriceZone("potential_reversal_zone",d[1]-tr*0.25,d[1]+tr*0.25,"confirmed",clamp(0.78-error*0.05),d[0],stop)
        confidence=clamp((0.75-min(0.15,error*0.04))*context.data_quality.score)
        return (StrategyEvidence(strategy_id=self.strategy_id,strategy_version=self.version,family=self.family,asset=context.asset,asset_class=context.asset_class,timeframe=context.timeframe,direction=direction,setup_type=matched,confidence=confidence,raw_score=confidence*100,zones=(prz,),entry_proposal=closes[-1],stop_proposal=stop,target_proposals=targets(closes[-1],stop,direction.value),invalidation=f"D point invalidated beyond {stop:.8g}",regime_compatibility=0.72,data_quality=context.data_quality,evidence={"points":{"X":x[:2],"A":a[:2],"B":b[:2],"C":c[:2],"D":d[:2]},"ratios":{"AB_XA":ratios[0],"BC_AB":ratios[1],"CD_BC":ratios[2],"XD_XA":ratios[3]},"ratio_error":error},duplicate_fingerprint=fingerprint({"a":context.asset,"tf":context.timeframe,"f":self.family,"p":matched,"pts":[round(v[1],8) for v in (x,a,b,c,d)]})),)
