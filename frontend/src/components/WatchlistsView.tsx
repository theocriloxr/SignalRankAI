"use client";

import { useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, rows, timeLabel, type Row } from "../lib/presentation";

function WatchlistPanel({item,onChanged}:{item:Row;onChanged:()=>void}){
  const id=display(item.watchlist_id,"");
  const [query,setQuery]=useState("");
  const [results,setResults]=useState<Row[]|null>(null);
  const [searching,setSearching]=useState(false);
  const [adding,setAdding]=useState("");
  const [message,setMessage]=useState("");
  const existing=new Set(rows(item.items).map(x=>display(x.instrument_id,"")).filter(Boolean));

  async function search(e:FormEvent<HTMLFormElement>){
    e.preventDefault();if(searching)return;
    const q=query.trim();
    if(q.length<2){setMessage("Enter at least two characters of an instrument.");return;}
    setSearching(true);setMessage("");setResults(null);
    try{
      const res=await client.GET("/api/v1/platform/instruments/search",{params:{query:{q,limit:12}}});
      if(res.response.ok && res.data)setResults(rows(res.data.instruments));
      else setMessage(res.response.status===401?"Your session has expired.":"Instrument search is unavailable. Try again.");
    }catch{setMessage("Could not verify any instruments at this time.");}
    finally{setSearching(false);}
  }
  async function add(instrumentId:string){
    if(!id||!instrumentId||adding)return;
    setAdding(instrumentId);setMessage("");
    try{
      const r=await client.POST("/api/v1/platform/watchlists/{watchlist_id}/items",{
        params:{path:{watchlist_id:id}},body:{instrument_id:instrumentId},
      });
      if(r.response.ok && r.data && r.data.added===true){
        setMessage("Instrument added to your account watchlist.");
        onChanged();
      }else setMessage(r.response.status===404?"The instrument or watchlist is no longer available. Refresh and search again.":"The service did not confirm this addition.");
    }catch{setMessage("Could not confirm the watchlist update.");}
    finally{setAdding("");}
  }

  return <article className="sr-data-panel sr-watchlist-panel">
    <header><p className="sr-overline">{item.is_default===true?"Default watchlist":"Account watchlist"}</p>
      <h2>{display(item.name,"Untitled watchlist")}</h2></header>
    <p>Created {timeLabel(item.created_at)} · {existing.size} watched instruments</p>
    {existing.size>0?<ul className="sr-watchlist-symbols">{Array.from(existing).map(symbol=><li key={symbol}>{symbol}</li>)}</ul>
      :<p>No instruments added yet.</p>}
    <form onSubmit={search} className="sr-create-form" role="search">
      <label>Search the canonical instrument directory
        <input name="instrument_search" value={query} onChange={e=>setQuery(e.target.value)} maxLength={80} minLength={2} required placeholder="BTCUSD, EURUSD, XAUUSD…" autoComplete="off"/>
      </label>
      <button className="sr-secondary-action" disabled={searching||!id} type="submit">{searching?"Searching…":"Find instruments"}</button>
    </form>
    {results!==null&&<section className="sr-watchlist-results" aria-label="Instrument search results">
      <p>{results.length? "Matching active instruments — choose one to watch:":"No matching active instruments were returned."}</p>
      {results.map((instrument,i)=>{
        const instrumentId=display(instrument.instrument_id,"");
        const watched=existing.has(instrumentId);
        return <div className="sr-watchlist-result" key={instrumentId||String(i)}>
          <div><strong>{display(instrument.display_symbol,display(instrument.canonical_symbol,"Instrument"))}</strong>
            <small>{display(instrument.asset_class)} · {display(instrument.instrument_type)} · {instrument.tradable===true?"Market data marked tradable":"Trading eligibility not confirmed"}</small></div>
          <button className="sr-secondary-action" type="button" disabled={!instrumentId||watched||Boolean(adding)} onClick={()=>add(instrumentId)}>{watched?"Already watched":adding===instrumentId?"Adding…":"Add to watchlist"}</button>
        </div>;
      })}
    </section>}
    {message&&<p className="sr-submit-feedback" role="status">{message}</p>}
    <p className="sr-overline">A watchlist does not authorize or initiate a broker order.</p>
  </article>;
}

export function WatchlistsView({data,onChanged}:{data:Row;onChanged:()=>void}){
  const items=rows(data.watchlists);
  return <div className="sr-view-stack">
    <p className="sr-risk-note">Watchlists belong to your account. Instruments are matched against the canonical active directory. Watching an instrument does not enable execution or bypass plan limits.</p>
    {items.length ? <div className="sr-record-grid">{items.map((x,i)=><WatchlistPanel key={display(x.watchlist_id,String(i))} item={x} onChanged={onChanged}/>)}</div>:
    <div className="sr-empty"><strong>No watchlists were returned.</strong><p>Create one below to follow recognized instruments. This does not activate any trading feature.</p></div>}
  </div>;
}
