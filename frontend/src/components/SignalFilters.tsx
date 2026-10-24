"use client";

import { useState, type FormEvent } from "react";
import { Icon } from "./ui/Icon";

export type SignalQuery = {
  asset?: string;
  asset_class?: string;
  timeframe?: string;
  strategy?: string;
};

/** Filters only narrow the delivered-receipt query; they never change generation or risk gates. */
export function SignalFilters({ onApply }: { onApply: (next: SignalQuery)=>void }) {
  const [expanded,setExpanded]=useState(false);
  const [active,setActive]=useState(0);
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields=new FormData(event.currentTarget);
    const asset=String(fields.get("asset")||"").trim().toUpperCase().replace(/[^A-Z0-9._/-]/g,"").slice(0,32);
    const assetClass=String(fields.get("asset_class")||"");
    const timeframe=String(fields.get("timeframe")||"");
    const strategy=String(fields.get("strategy")||"").trim().slice(0,64);
    const next={
      ...(asset?{asset}:{}),
      ...(assetClass?{asset_class:assetClass}:{}),
      ...(timeframe?{timeframe}:{}),
      ...(strategy?{strategy}:{}),
    };
    setActive(Object.keys(next).length);
    onApply(next);
  }
  return <div className="ws-stack">
    <div className="ui-actions">
      <button className="ui-btn" aria-expanded={expanded} aria-controls="ws-signal-filters" type="button" onClick={()=>setExpanded(!expanded)}>
        <Icon name="filter"/>{expanded?"Hide filters":"Filter signals"}{active>0&&<span className="ui-badge ui-badge--brand ui-badge--plain">{active}</span>}
      </button>
    </div>
    {expanded&&<form id="ws-signal-filters" onSubmit={apply} className="ui-card">
      <div className="ui-form-grid">
        <label className="ui-field">Instrument<input className="ui-input mono" name="asset" maxLength={32} placeholder="e.g. XAUUSD, BTCUSDT" autoComplete="off"/></label>
        <label className="ui-field">Asset class<select className="ui-select" name="asset_class" defaultValue="">
          <option value="">All entitled classes</option><option value="crypto">Crypto</option><option value="fx">FX</option><option value="index">Indices</option><option value="stock">Stocks</option><option value="commodity">Commodities</option>
        </select></label>
        <label className="ui-field">Timeframe<select className="ui-select" name="timeframe" defaultValue="">
          <option value="">Any timeframe</option>
          {["5m","15m","30m","1h","4h","1d","1w"].map(time=><option key={time} value={time}>{time}</option>)}
        </select></label>
        <label className="ui-field">Strategy name contains<input className="ui-input" name="strategy" maxLength={64} placeholder="Strategy filter"/></label>
      </div>
      <div className="ui-actions">
        <button type="submit" className="ui-btn ui-btn--primary">Apply filters</button>
        <button type="reset" className="ui-btn ui-btn--ghost" onClick={()=>{setActive(0);onApply({});}}>Clear</button>
      </div>
      <p className="ui-muted">Filters narrow your delivered-signal history. They never change signal generation or risk gates.</p>
    </form>}
  </div>;
}
