"use client";

import { useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, record } from "../lib/presentation";

const PHRASE = "DELETE MY ACCOUNT";

/** Data export and deletion requests. Deletion opens a review; nothing is erased here. */
export function PrivacyCenter({onChanged}:{onChanged:()=>void}){
  const [exporting,setExporting]=useState(false);
  const [phrase,setPhrase]=useState("");
  const [reason,setReason]=useState("");
  const [busy,setBusy]=useState(false);
  const [retained,setRetained]=useState<string[]>([]);
  const [notice,setNotice]=useState("");
  const [error,setError]=useState(false);

  function respond(text:string,failed=false){setNotice(text);setError(failed);}

  async function download(){
    if(exporting)return;
    setExporting(true);respond("");
    try{
      const r=await client.GET("/api/v1/platform/account/export");
      if(!r.response.ok||!r.data){respond(r.response.status===401?"Your session expired. Sign in again.":"The export could not be prepared. Retry later.",true);return;}
      const blob=new Blob([JSON.stringify(r.data,null,2)],{type:"application/json"});
      const url=URL.createObjectURL(blob);
      const link=document.createElement("a");
      link.href=url;link.download=`signalrank-account-export-${new Date().toISOString().slice(0,10)}.json`;
      document.body.appendChild(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
      const missing=Object.keys(record(record(r.data).unavailable));
      respond(missing.length?`Export downloaded. Not included by your plan: ${missing.join(", ").replaceAll("_"," ")}.`:"Export downloaded.");
    }catch{respond("The export could not be verified. Retry later.",true);}
    finally{setExporting(false);}
  }

  async function requestDeletion(e:FormEvent<HTMLFormElement>){
    e.preventDefault();if(busy)return;
    if(phrase.trim()!==PHRASE)return respond(`Type ${PHRASE} exactly to confirm.`,true);
    setBusy(true);respond("");
    try{
      const body=reason.trim()?{confirm_phrase:PHRASE,reason:reason.trim().slice(0,2000)}:{confirm_phrase:PHRASE};
      const r=await client.POST("/api/v1/platform/account/deletion-request",{body});
      const data=record(r.data);
      if(r.response.ok&&display(data.ticket_id,"")){
        setRetained(Array.isArray(data.retained_records)?data.retained_records.filter((v):v is string=>typeof v==="string"):[]);
        setPhrase("");setReason("");
        respond(data.already_requested===true?"A deletion review is already open for this account. Support will reply on that ticket.":"Deletion review opened. Support will confirm by ticket before anything is removed.");
        onChanged();
      }else respond(r.response.status===403?"For your protection this needs a fresh sign-in. Sign out, sign back in, then retry within 15 minutes.":r.response.status===401?"Your session expired. Sign in again.":"The request was not confirmed. Retry later.",true);
    }catch{respond("The request could not be verified. Retry later.",true);}
    finally{setBusy(false);}
  }

  return <section className="ui-card" aria-labelledby="privacy-title">
    <p className="ui-eyebrow">PRIVACY</p>
    <h2 id="privacy-title">Your data</h2>
    <p>Download a copy of the data held for your account. Passwords, session tokens, full API keys and broker credentials are never included.</p>
    <div className="ui-actions"><button className="ui-btn" type="button" disabled={exporting} onClick={download}>{exporting?"Preparing…":"Download my data (JSON)"}</button></div>

    <h3>Request account deletion</h3>
    <p>This opens a support review rather than deleting immediately, so open positions, subscriptions and payments can be settled first. Some records must be kept for reconciliation and security; the review explains which.</p>
    <form className="ui-form" onSubmit={requestDeletion}>
      <label className="ui-field">Type {PHRASE} to confirm
        <input className="ui-input" type="text" autoComplete="off" spellCheck={false} maxLength={64} value={phrase} onChange={e=>setPhrase(e.target.value)}/>
      </label>
      <label className="ui-field">Reason (optional)
        <textarea className="ui-textarea" rows={3} maxLength={2000} value={reason} onChange={e=>setReason(e.target.value)}/>
      </label>
      <button className="ui-btn" type="submit" disabled={busy||phrase.trim()!==PHRASE}>{busy?"Submitting…":"Request deletion review"}</button>
    </form>
    {notice&&<p className={error?"ui-feedback ui-feedback--error":"ui-feedback"} role={error?"alert":"status"}>{notice}</p>}
    {retained.length>0&&<div className="ui-notice ui-notice--neutral"><p>Kept after deletion where the law or reconciliation requires:</p><ul>{retained.map(r=><li key={r}>{r}</li>)}</ul></div>}
  </section>;
}
