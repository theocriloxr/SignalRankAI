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
      }catch{if(!cancelled)setState({kind:"error",rows:[],message:"Instrument discovery is temporarily unavailable. No quotes or venue coverage has been inferred."});}
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

  return <section className="sr-data-panel sr-market-directory" aria-labelledby="sr-market-directory-title">
    <div className="sr-section-head"><div>
      <p className="sr-overline">Canonical market universe / Provider-backed inventory</p>
      <h2 id="sr-market-directory-title">Discover instruments</h2>
    </div><span className="sr-state">SOURCE DISCOVERY · NOT LIVE PRICING</span></div>
    <p className="sr-risk-note">Only active instrument identities returned by your canonical platform appear here. Provider counts describe stored mappings, not a currently healthy price feed or authorization to trade.</p>
    <form className="sr-market-search" role="search" onSubmit={submit}>
      <label>Instrument, symbol or underlying<input value={query} onChange={e=>setQuery(e.target.value)} maxLength={80} autoComplete="off" placeholder="e.g. EURUSD, BTCUSDT, XAUUSD"/></label>
      <label>Market class<select value={assetClass} onChange={e=>setAssetClass(e.target.value)}>
        {classOptions.map(([value,label])=><option key={value} value={value}>{label}</option>)}
      </select></label>
      <button className="button" type="submit">Search instruments</button>
      <button className="sr-secondary-action" type="button" onClick={()=>{setQuery("");setAssetClass("");setSearch({q:"",asset_class:""});setVersion(v=>v+1);setState({kind:"loading",rows:[],message:""});}}>Clear</button>
    </form>
    {state.kind==="loading"&&<div className="sr-loading" role="status">Retrieving canonical instrument records…</div>}
    {state.kind==="error"&&<div className="sr-access-state" role="alert"><p>{state.message}</p><button type="button" className="sr-secondary-action" onClick={()=>{setState({kind:"loading",rows:[],message:""});setVersion(v=>v+1);}}>Retry discovery</button></div>}
    {state.kind==="ready"&&<>
      <div className="sr-list-actions"><span>{state.rows.length} records in this response · maximum 30 · global universe count not provided</span></div>
      {state.rows.length?<div className="sr-market-results">{state.rows.map((instrument,i)=>{
        const providers=Array.isArray(instrument.providers)?instrument.providers.filter((v):v is string=>typeof v==="string"&&v.trim().length>0):[];
        const venues=Array.isArray(instrument.venues)?instrument.venues.filter((v):v is string=>typeof v==="string"&&v.trim().length>0):[];
        return <article key={display(instrument.instrument_id,String(i))} className="sr-market-instrument">
          <div className="sr-market-title"><div>
            <p className="sr-overline">{display(instrument.asset_class)} / {display(instrument.instrument_type)}</p>
            <h3>{display(instrument.display_symbol,display(instrument.canonical_symbol,"Unidentified asset"))}</h3>
            <span className="sr-market-canonical">{display(instrument.canonical_symbol)}</span>
          </div><span className="sr-state">{instrument.tradable===true?"Mapped tradable flag":instrument.tradable===false?"Not marked tradable":"Tradability unverified"}</span></div>
          <dl><div className="sr-data-pair"><dt>Provider mappings</dt><dd>{numberLabel(instrument.provider_count,0)}</dd></div>
            <div className="sr-data-pair"><dt>Price tick size</dt><dd>{numberLabel(instrument.tick_size,8)}</dd></div>
            <div className="sr-data-pair"><dt>Quantity step</dt><dd>{numberLabel(instrument.quantity_step,8)}</dd></div>
            <div className="sr-data-pair"><dt>Discovery</dt><dd>{display(instrument.discovery_status)}</dd></div></dl>
          {providers.length>0&&<div className="sr-market-chips" aria-label="Mapped providers">{providers.slice(0,8).map((v,j)=><span key={v+j}>{v}</span>)}</div>}
          {venues.length>0&&<p className="sr-muted">Mapped venues: {venues.slice(0,8).join(" · ")}</p>}
          <p className="sr-overline">Mapping evidence only — session, quote and account eligibility separately gated</p>
        </article>;
      })}</div>:<div className="sr-empty"><strong>No active instruments matched the search.</strong><p>The directory did not report any matching records. This does not indicate that a market is closed or that every data provider is unavailable.</p></div>}
    </>}
  </section>;
}
