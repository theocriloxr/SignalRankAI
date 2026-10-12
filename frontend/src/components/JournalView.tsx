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
      else {setError(result.response.status===404?"This entry no longer exists. Refresh the page.":"Deletion was not confirmed. No success has been assumed.");setConfirming(false);}
    }catch{setError("The deletion result could not be verified. Check your connection.");setConfirming(false);}
    finally{setBusy(false);}
  }
  return <article className="sr-data-panel sr-journal-entry">
    <div className="sr-journal-top"><div><p className="sr-overline">{timeLabel(entry.occurred_at)} / Personal trading journal</p>
      <h2>{display(entry.title,"Untitled reflection")}</h2></div><span className="sr-state">{display(entry.emotion,"Self-recorded")}</span></div>
    <p className="sr-journal-notes">{display(entry.notes,"No notes entered.")}</p>
    <dl><div className="sr-data-pair"><dt>Result (R)</dt><dd>{numberLabel(entry.result_r,3)}</dd></div>
      <div className="sr-data-pair"><dt>Plan adherence</dt><dd>{finite(entry.plan_adherence)===null?"Unavailable":`${numberLabel(entry.plan_adherence,0)}%`}</dd></div>
      <div className="sr-data-pair"><dt>Reflection category</dt><dd>{display(entry.mistake_category)}</dd></div></dl>
    {tags.length>0&&<div className="sr-watchlist-symbols">{tags.map((tag,i)=><span key={i}>{tag}</span>)}</div>}
    <footer>{signal&&<Link href={`/app/signals/${encodeURIComponent(signal)}`}>View linked signal evidence →</Link>}
      {!confirming?<button type="button" className="sr-secondary-action" disabled={!id} onClick={()=>setConfirming(true)}>Delete journal entry</button>:
       <div className="sr-journal-delete-confirm" role="group" aria-label="Confirm permanent journal deletion">
        <span>Delete this journal entry permanently?</span>
        <button type="button" disabled={busy} className="sr-secondary-action" onClick={()=>setConfirming(false)}>Keep entry</button>
        <button type="button" disabled={busy} className="sr-secondary-action" onClick={remove}>{busy?"Deleting…":"Confirm deletion"}</button>
       </div>}
    </footer>
    {error&&<p role="alert" className="sr-submit-feedback sr-submit-feedback--error">{error}</p>}
  </article>;
}

export function JournalView({data,onChanged}:{data:Row;onChanged:()=>void}){
  const entries=rows(data.entries);
  return <section className="sr-view-stack">
    <p className="sr-risk-note">Your last {entries.length} personal reflections returned by the account service. Journal notes are self-reported and are not independent evidence of profit, broker fills or certified execution.</p>
    {entries.length?<div className="sr-record-grid">{entries.map((entry,i)=><Entry key={display(entry.journal_entry_id,String(i))} entry={entry} onChanged={onChanged}/>)}</div>:
     <div className="sr-empty"><strong>No journal entries were returned.</strong><p>Add a reflection below. This does not trigger signal generation or submit an order.</p></div>}
  </section>;
}
