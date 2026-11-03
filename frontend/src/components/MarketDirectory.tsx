"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, numberLabel, rows, statusText, type Row } from "../lib/presentation";

type Directory={kind:"loading"|"ready"|"error";rows:Row[];message:string};
const classOptions=[
  ["","All asset classes"],["crypto","Crypto"],["fx","Forex"],["stock","Equities"],["index","Indices"],["commodity","Commodities"]
] as const;

/** Canonical instrument discovery. Market existence/tradability is never
 * treated as an execution entitlement or proof of current live quotes. */
export function MarketDirectory(){
  const [query,setQuery]=useState("");
  const [assetClass,setAssetClass]=useState("");
  const [search,setSearch]=useState({q:"",asset_class:""});
  const [version,setVersion]=useState(0);
  const [state,setState]=useState<Directory>({kind:"loading",rows:[],message:""});

  useEffect(()=>{
    let cancelled=false;
    async function load(){
      try{
        const response=await client.GET("/api/v1/platform/instruments/search",{
          params:{query:{
            q:search.q,limit:30,...(search.asset_class?{asset_class:search.asset_class}:{})
          }}
        });
        if(cancelled)return;
        if(response.response.ok&&response.data){
          setState({kind:"ready",rows:rows(response.data.instruments),message:""});
        }else setState({kind:"error",rows:[],message:statusText(response.response.status)});
      }catch{if(!cancelled)setState({kind:"error",rows:[],message:"Instrument search isn't available right now. Try again in a moment."});}
    }
    void load();
    return ()=>{cancelled=true;};
  },[search,version]);

  function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    const q=query.trim().slice(0,80);
    setState({kind:"loading",rows:[],message:""});
    setSearch({q,asset_class:assetClass});
    setVersion(v=>v+1);
  }

  return <section className="ui-card" aria-labelledby="sr-market-directory-title">
    <div className="ui-card-head"><div>
      
      <h2 id="sr-market-directory-title">Find an instrument</h2>
    </div><span className="ui-badge">Search</span></div>
    <p className="ws-aside">Every instrument we can track. The provider count says how many data sources know the symbol, not that prices are flowing right now.</p>
    <form className="ws-searchbar" role="search" onSubmit={submit}>
      <label className="ui-field">Instrument, symbol or underlying<input className="ui-input" value={query} onChange={e=>setQuery(e.target.value)} maxLength={80} autoComplete="off" placeholder="e.g. EURUSD, BTCUSDT, XAUUSD"/></label>
      <label className="ui-field">Market class<select className="ui-select" value={assetClass} onChange={e=>setAssetClass(e.target.value)}>
        {classOptions.map(([value,label])=><option key={value} value={value}>{label}</option>)}
      </select></label>
      <button className="ui-btn ui-btn--primary" type="submit">Search instruments</button>
      <button className="ui-btn" type="button" onClick={()=>{setQuery("");setAssetClass("");setSearch({q:"",asset_class:""});setVersion(v=>v+1);setState({kind:"loading",rows:[],message:""});}}>Clear</button>
    </form>
    {state.kind==="loading"&&<div className="ui-loading" role="status">Searching…</div>}
    {state.kind==="error"&&<div className="ui-state" role="alert"><p>{state.message}</p><button type="button" className="ui-btn" onClick={()=>{setState({kind:"loading",rows:[],message:""});setVersion(v=>v+1);}}>Try again</button></div>}
    {state.kind==="ready"&&<>
      <div className="ui-pagination"><span>{state.rows.length} records in this response · maximum 30 · global universe count not provided</span></div>
      {state.rows.length?<div className="ws-stack">{state.rows.map((instrument,i)=>{
        const providers=Array.isArray(instrument.providers)?instrument.providers.filter((v):v is string=>typeof v==="string"&&v.trim().length>0):[];
        const venues=Array.isArray(instrument.venues)?instrument.venues.filter((v):v is string=>typeof v==="string"&&v.trim().length>0):[];
        return <article key={display(instrument.instrument_id,String(i))} className="ws-instrument">
          <div className="ws-instrument-head"><div>
            <p className="ui-eyebrow">{display(instrument.asset_class)} · {display(instrument.instrument_type)}</p>
            <h3>{display(instrument.display_symbol,display(instrument.canonical_symbol,"Unnamed instrument"))}</h3>
            <span className="mono ui-muted">{display(instrument.canonical_symbol)}</span>
          </div><span className="ui-badge">{instrument.tradable===true?"Tradable":instrument.tradable===false?"Not tradable":"Not known"}</span></div>
          <dl className="ui-kv"><div className="ui-kv-row"><dt>Data sources</dt><dd>{numberLabel(instrument.provider_count,0)}</dd></div>
            <div className="ui-kv-row"><dt>Price step</dt><dd>{numberLabel(instrument.tick_size,8)}</dd></div>
            <div className="ui-kv-row"><dt>Quantity step</dt><dd>{numberLabel(instrument.quantity_step,8)}</dd></div>
            <div className="ui-kv-row"><dt>Discovery</dt><dd>{display(instrument.discovery_status)}</dd></div></dl>
          {providers.length>0&&<div className="ui-chip-row" aria-label="Sources">{providers.slice(0,8).map((v,j)=><span key={v+j}>{v}</span>)}</div>}
          {venues.length>0&&<p className="ui-muted">Mapped venues: {venues.slice(0,8).join(" · ")}</p>}
          <p className="ui-eyebrow">Which data providers know this symbol. Trading hours and prices are checked separately.</p>
        </article>;
      })}</div>:<div className="ui-empty"><strong>Nothing matched that search.</strong><p>Try the symbol without separators, such as XAUUSD or BTCUSDT.</p></div>}
    </>}
  </section>;
}
