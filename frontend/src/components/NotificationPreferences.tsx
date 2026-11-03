"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { record, statusText, type Row } from "../lib/presentation";

const channels=[
  {key:"web_enabled",label:"Web notifications"},
  {key:"telegram_enabled",label:"Telegram notifications"},
  {key:"email_enabled",label:"Email notifications"},
  {key:"push_enabled",label:"Push notifications"},
] as const;
type Channel = typeof channels[number]["key"];
type Choice = "keep" | "on" | "off";
type Selections = Record<Channel,Choice>;
const emptySelections:Selections={web_enabled:"keep",telegram_enabled:"keep",email_enabled:"keep",push_enabled:"keep"};

export function NotificationPreferences(){
  const [current,setCurrent]=useState<Row|null>(null);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [choices,setChoices]=useState<Selections>(emptySelections);
  const [message,setMessage]=useState("");
  useEffect(()=>{
    let cancelled=false;
    async function load(){
      try{
        const r=await client.GET("/api/v1/platform/notifications/preferences");
        if(cancelled)return;
        if(r.response.ok && r.data)setCurrent(record(r.data.preferences));
        else setError(statusText(r.response.status));
      }catch{if(!cancelled)setError("We couldn't load your notification settings.");}
      finally{if(!cancelled)setLoading(false);}
    }
    void load();
    return ()=>{cancelled=true;};
  },[]);

  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(saving||!current)return;
    const selected=channels.filter(c=>choices[c.key]!=="keep");
    if(!selected.length){setMessage("Change at least one channel first.");return;}
    const body:Partial<Record<Channel,boolean>>={};
    for(const channel of selected)body[channel.key]=choices[channel.key]==="on";
    setSaving(true);setMessage("");
    try{
      const r=await client.PUT("/api/v1/platform/notifications/preferences",{body});
      if(r.response.ok && r.data){
        setCurrent(record(r.data.preferences));
        setChoices(emptySelections);
        setMessage("Saved.");
      }else setMessage(r.response.status===401?"Your session expired. Sign in again.":"That didn't save. Try again.");
    }catch{setMessage("We couldn't confirm the change. Check your connection and refresh.");}
    finally{setSaving(false);}
  }
  return <section className="ui-card" aria-labelledby="sr-notification-preferences">
    <h2 id="sr-notification-preferences">Where we send notifications</h2>
    <p>Only the channels you change are saved. Quiet hours and the rest stay as they are.</p>
    {loading&&<p role="status">Loading…</p>}
    {error&&<p role="alert" className="ui-feedback ui-feedback--error">{error}</p>}
    {current&&<form className="ui-form" onSubmit={submit}>
      <div className="ws-pref-grid">
      {channels.map(c=><label key={c.key} className="ws-pref-row">
        <span><strong>{c.label}</strong><small>Current: {current[c.key]===true?"Enabled":current[c.key]===false?"Disabled":"Not reported"}</small></span>
        <select className="ui-select" aria-label={`Change ${c.label}`} value={choices[c.key]} onChange={e=>setChoices(v=>({...v,[c.key]:e.target.value as Choice}))}>
          <option value="keep">Keep as is</option>
          <option value="on">Enable</option>
          <option value="off">Disable</option>
        </select>
      </label>)}
      </div>
      <button type="submit" className="ui-btn ui-btn--primary" disabled={saving}>{saving?"Saving…":"Save"}</button>
      {message&&<p className="ui-feedback" role="status">{message}</p>}
    </form>}
  </section>;
}
