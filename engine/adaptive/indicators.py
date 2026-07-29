from __future__ import annotations

from engine.adaptive.types import Direction, MarketContext, StrategyEvidence, clamp, safe_float
from .helpers import atr, fingerprint, ohlcv, targets


class IndicatorComponent:
    strategy_id="adaptive.indicators";version="1.0.0";family="indicators"
    def evaluate(self, context: MarketContext)->tuple[StrategyEvidence,...]:
        if not context.data_quality.usable or len(context.candles)<30:return ()
        _,_,_,closes,_=ohlcv(context.candles);ind=context.indicators or {}
        fast=safe_float(ind.get("ema_fast",ind.get("ema_20")));slow=safe_float(ind.get("ema_slow",ind.get("ema_50")));rsi=safe_float(ind.get("rsi"),50);adx=safe_float(ind.get("adx"),0);macd=safe_float(ind.get("macd_histogram",ind.get("macd",0)))
        long_votes=sum([fast>slow>0,rsi>=52,macd>0,adx>=18]);short_votes=sum([0<fast<slow,rsi<=48,macd<0,adx>=18])
        if max(long_votes,short_votes)<3:return ()
        direction=Direction.LONG if long_votes>short_votes else Direction.SHORT;tr=max(atr(context.candles),abs(closes[-1])*0.001);stop=closes[-1]-tr*1.5 if direction is Direction.LONG else closes[-1]+tr*1.5
        confidence=clamp((0.58+max(long_votes,short_votes)*0.05)*context.data_quality.score)
        return (StrategyEvidence(strategy_id=self.strategy_id,strategy_version=self.version,family=self.family,asset=context.asset,asset_class=context.asset_class,timeframe=context.timeframe,direction=direction,setup_type="contextual_indicator_confluence",confidence=confidence,raw_score=confidence*100,entry_proposal=closes[-1],stop_proposal=stop,target_proposals=targets(closes[-1],stop,direction.value),invalidation="indicator structure and price invalidation",regime_compatibility=0.75,data_quality=context.data_quality,evidence={"ema_fast":fast,"ema_slow":slow,"rsi":rsi,"adx":adx,"macd":macd,"long_votes":long_votes,"short_votes":short_votes,"settings_source":"runtime_indicators"},duplicate_fingerprint=fingerprint({"a":context.asset,"tf":context.timeframe,"f":self.family,"d":direction.value,"b":round(closes[-1],8)})),)
