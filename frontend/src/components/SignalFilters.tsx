"use client";

import { useState, type FormEvent } from "react";

export type SignalQuery = {
  asset?: string;
  asset_class?: string;
  timeframe?: string;
  strategy?: string;
};

export function SignalFilters({ onApply }: { onApply: (next: SignalQuery)=>void }) {
  const [expanded,setExpanded]=useState(false);
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields=new FormData(event.currentTarget);
    const asset=String(fields.get("asset")||"").trim().toUpperCase().replace(/[^A-Z0-9._/-]/g,"").slice(0,32);
    const assetClass=String(fields.get("asset_class")||"");
    const timeframe=String(fields.get("timeframe")||"");
    const strategy=String(fields.get("strategy")||"").trim().slice(0,64);
    onApply({
      ...(asset?{asset}:{}),
      ...(assetClass?{asset_class:assetClass}:{}),
      ...(timeframe?{timeframe}:{}),
      ...(strategy?{strategy}:{}),
    });
  }
  return <div className="sr-filter-block">
    <button className="sr-secondary-action" aria-expanded={expanded} type="button" onClick={()=>setExpanded(!expanded)}>
      {expanded?"Hide signal filters":"Filter delivered signals"}
    </button>
    {expanded&&<form onSubmit={apply} className="sr-filter-form">
      <label>Instrument<input name="asset" maxLength={32} placeholder="e.g. XAUUSD, BTCUSDT" autoComplete="off"/></label>
      <label>Asset class<select name="asset_class" defaultValue="">
        <option value="">All entitled classes</option><option value="crypto">Crypto</option><option value="fx">FX</option><option value="index">Indices</option><option value="stock">Stocks</option><option value="commodity">Commodities</option>
      </select></label>
      <label>Timeframe<select name="timeframe" defaultValue="">
        <option value="">Any timeframe</option>
        {["5m","15m","30m","1h","4h","1d","1w"].map(time=><option key={time} value={time}>{time}</option>)}
      </select></label>
      <label>Strategy name contains<input name="strategy" maxLength={64} placeholder="Strategy filter"/></label>
      <button type="submit" className="button">Apply filters</button>
      <button type="reset" className="sr-secondary-action" onClick={()=>onApply({})}>Clear filters</button>
      <p>Filters apply to the latest 30 delivered signals from your canonical account. They never change signal generation or risk gates.</p>
    </form>}
  </div>;
}
