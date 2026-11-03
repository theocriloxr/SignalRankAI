"use client";

import Link from "next/link";
import { useState } from "react";
import client from "../lib/client";
import { display, finite, numberLabel, rows, timeLabel, type Row } from "../lib/presentation";

function Entry({entry,onChanged}:{entry:Row;onChanged:()=>void}){
  const [confirming,setConfirming]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const id=display(entry.journal_entry_id,"");
  const signal=display(entry.signal_id,"");
  const tags=Array.isArray(entry.tags)?entry.tags.filter((t):t is string=>typeof t==="string"&&t.trim().length>0):[];
  async function remove(){
    if(!id||busy||!confirming)return;
    setBusy(true);setError("");
    try{
      const result=await client.DELETE("/api/v1/platform/journal/{journal_entry_id}",{
        params:{path:{journal_entry_id:id}},
      });
      if(result.response.ok&&result.data&&result.data.deleted===true)onChanged();
      else {setError(result.response.status===404?"This entry no longer exists. Refresh the page.":"The entry wasn't deleted. Try again.");setConfirming(false);}
    }catch{setError("We couldn't confirm the deletion. Refresh to check.");setConfirming(false);}
    finally{setBusy(false);}
  }
  return <article className="ui-card">
    <div className="ui-card-head"><div><p className="ui-eyebrow">{timeLabel(entry.occurred_at)}</p>
      <h2>{display(entry.title,"Untitled entry")}</h2></div><span className="ui-badge">{display(entry.emotion,"Self-recorded")}</span></div>
    <p>{display(entry.notes,"No notes.")}</p>
    <dl className="ui-kv"><div className="ui-kv-row"><dt>Result (R)</dt><dd>{numberLabel(entry.result_r,3)}</dd></div>
      <div className="ui-kv-row"><dt>Followed the plan</dt><dd>{finite(entry.plan_adherence)===null?"Unavailable":`${numberLabel(entry.plan_adherence,0)}%`}</dd></div>
      <div className="ui-kv-row"><dt>Category</dt><dd>{display(entry.mistake_category)}</dd></div></dl>
    {tags.length>0&&<div className="ui-chip-row">{tags.map((tag,i)=><span key={i}>{tag}</span>)}</div>}
    <footer>{signal&&<Link href={`/app/signals/${encodeURIComponent(signal)}`}>Open the signal →</Link>}
      {!confirming?<button type="button" className="ui-btn" disabled={!id} onClick={()=>setConfirming(true)}>Delete</button>:
       <div className="ui-confirm" role="group" aria-label="Delete this entry?">
        <span>It can&rsquo;t be recovered.</span>
        <button type="button" disabled={busy} className="ui-btn" onClick={()=>setConfirming(false)}>Keep entry</button>
        <button type="button" disabled={busy} className="ui-btn" onClick={remove}>{busy?"Deleting…":"Confirm deletion"}</button>
       </div>}
    </footer>
    {error&&<p role="alert" className="ui-feedback ui-feedback--error">{error}</p>}
  </article>;
}

export function JournalView({data,onChanged}:{data:Row;onChanged:()=>void}){
  const entries=rows(data.entries);
  return <section className="ws-stack">
    <p className="ws-aside">Your last {entries.length} entries. Only you write these, so they&rsquo;re a record of what you thought, not proof of what traded.</p>
    {entries.length?<div className="ws-cards">{entries.map((entry,i)=><Entry key={display(entry.journal_entry_id,String(i))} entry={entry} onChanged={onChanged}/>)}</div>:
     <div className="ui-empty"><strong>No journal entries yet.</strong><p>Write one below after your next trade.</p></div>}
  </section>;
}
