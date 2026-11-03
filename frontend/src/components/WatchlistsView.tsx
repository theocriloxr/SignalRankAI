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
  const [removing,setRemoving]=useState("");
  const [confirmDelete,setConfirmDelete]=useState(false);
  const [deleting,setDeleting]=useState(false);
  const name=display(item.name,"Untitled watchlist");
  const watched=rows(item.items).map(x=>({id:display(x.instrument_id,""),label:display(x.display_symbol,display(x.instrument_id,""))})).filter(x=>x.id);
  const existing=new Set(watched.map(x=>x.id));

  async function search(e:FormEvent<HTMLFormElement>){
    e.preventDefault();if(searching)return;
    const q=query.trim();
    if(q.length<2){setMessage("Enter at least two characters of an instrument.");return;}
    setSearching(true);setMessage("");setResults(null);
    try{
      const res=await client.GET("/api/v1/platform/instruments/search",{params:{query:{q,limit:12}}});
      if(res.response.ok && res.data)setResults(rows(res.data.instruments));
      else setMessage(res.response.status===401?"Your session has expired.":"Instrument search is unavailable. Try again.");
    }catch{setMessage("Search didn't work just now. Try again.");}
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
        setMessage("Added.");
        onChanged();
      }else setMessage(r.response.status===404?"The instrument or watchlist is no longer available. Refresh and search again.":"That wasn't added. Try again.");
    }catch{setMessage("We couldn't confirm that change. Refresh to check.");}
    finally{setAdding("");}
  }
  async function remove(instrumentId:string,label:string){
    if(!id||removing)return;
    setRemoving(instrumentId);setMessage("");
    try{
      const r=await client.DELETE("/api/v1/platform/watchlists/{watchlist_id}/items/{instrument_id}",{
        params:{path:{watchlist_id:id,instrument_id:instrumentId}},
      });
      if(r.response.ok){setMessage(`${label} removed from ${name}.`);onChanged();}
      else setMessage(r.response.status===404?"That instrument is no longer on this list. Refresh to see the current list.":"That wasn't removed. Try again.");
    }catch{setMessage("We couldn't confirm that change. Refresh to check.");}
    finally{setRemoving("");}
  }
  async function deleteList(){
    if(!id||deleting)return;
    setDeleting(true);setMessage("");
    try{
      const r=await client.DELETE("/api/v1/platform/watchlists/{watchlist_id}",{params:{path:{watchlist_id:id}}});
      if(r.response.ok){onChanged();return;}
      setMessage(r.response.status===404?"This list was already deleted. Refresh to update.":"The list wasn't deleted. Try again.");
    }catch{setMessage("We couldn't confirm the deletion. Refresh to check.");}
    finally{setDeleting(false);setConfirmDelete(false);}
  }

  return <article className="ui-card">
    <header><p className="ui-eyebrow">{item.is_default===true?"Default":"Watchlist"}</p>
      <h2>{name}</h2></header>
    <p>Created {timeLabel(item.created_at)} · {existing.size} watched instruments</p>
    {watched.length>0?<ul className="ui-chip-row" aria-label={`Instruments on ${name}`}>{watched.map(x=><li key={x.id} className="ui-chip" title={x.id}>{x.label}
      <button type="button" className="ui-chip-remove" aria-label={`Remove ${x.label} from ${name}`} disabled={Boolean(removing)} onClick={()=>remove(x.id,x.label)}>×</button></li>)}</ul>
      :<p>No instruments added yet.</p>}
    <form onSubmit={search} className="ui-form" role="search">
      <label className="ui-field">Search the canonical instrument directory
        <input className="ui-input" name="instrument_search" value={query} onChange={e=>setQuery(e.target.value)} maxLength={80} minLength={2} required placeholder="BTCUSD, EURUSD, XAUUSD…" autoComplete="off"/>
      </label>
      <button className="ui-btn" disabled={searching||!id} type="submit">{searching?"Searching…":"Find instruments"}</button>
    </form>
    {results!==null&&<section className="ws-subsection" aria-label="Instrument search results">
      <p>{results.length? "Pick one to watch:":"Nothing matched."}</p>
      {results.map((instrument,i)=>{
        const instrumentId=display(instrument.instrument_id,"");
        const watched=existing.has(instrumentId);
        return <div className="ws-result-row" key={instrumentId||String(i)}>
          <div><strong>{display(instrument.display_symbol,display(instrument.canonical_symbol,"Instrument"))}</strong>
            <small>{display(instrument.asset_class)} · {display(instrument.instrument_type)} · {instrument.tradable===true?"Tradable":"Tradability not known"}</small></div>
          <button className="ui-btn" type="button" disabled={!instrumentId||watched||Boolean(adding)} onClick={()=>add(instrumentId)}>{watched?"Already watched":adding===instrumentId?"Adding…":"Add to watchlist"}</button>
        </div>;
      })}
    </section>}
    {message&&<p className="ui-feedback" role="status">{message}</p>}
    <div className="ui-actions">{confirmDelete?<>
      <button type="button" className="ui-btn ui-btn--danger" disabled={deleting} onClick={deleteList}>{deleting?"Deleting…":`Delete ${name} and its instruments`}</button>
      <button type="button" className="ui-btn" disabled={deleting} onClick={()=>setConfirmDelete(false)}>Cancel</button></>
      :<button type="button" className="ui-btn ui-btn--ghost" onClick={()=>setConfirmDelete(true)}>Delete watchlist</button>}</div>
    <p className="ui-muted">The same lists show up in Telegram under /watchlist.</p>
  </article>;
}

export function WatchlistsView({data,onChanged}:{data:Row;onChanged:()=>void}){
  const items=rows(data.watchlists);
  return <div className="ws-stack">
    <p className="ws-aside">Keep an eye on instruments without getting a signal for them. Watching doesn&rsquo;t place trades.</p>
    {items.length ? <div className="ws-cards">{items.map((x,i)=><WatchlistPanel key={display(x.watchlist_id,String(i))} item={x} onChanged={onChanged}/>)}</div>:
    <div className="ui-empty"><strong>No watchlists yet.</strong><p>Create one below.</p></div>}
  </div>;
}
