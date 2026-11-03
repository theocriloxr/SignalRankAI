"use client";

import { useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, finite, record, rows, timeLabel, type Row } from "../lib/presentation";

const alertKinds = [
  ["price_above","Price crosses above"],["price_below","Price crosses below"],
  ["signal_generated","New signal"],["entry_triggered","Entry triggered"],
  ["outcome","Signal result"],["provider_status","Data provider problem"],
] as const;
type Kind = typeof alertKinds[number][0];
const channels = ["web","telegram","email","push"] as const;
type Channel = typeof channels[number];
const needsPrice = (kind:Kind) => kind==="price_above"||kind==="price_below";

export function AlertRules({data,onChanged}:{data:Row;onChanged:()=>void}){
  const items=rows(data.alerts);
  const [asset,setAsset]=useState("");
  const [kind,setKind]=useState<Kind>("signal_generated");
  const [threshold,setThreshold]=useState("");
  const [selectedChannels,setSelectedChannels]=useState<Channel[]>(["web"]);
  const [busy,setBusy]=useState(false);
  const [deactivating,setDeactivating]=useState("");
  const [confirmId,setConfirmId]=useState("");
  const [notice,setNotice]=useState("");
  const [error,setError]=useState(false);

  async function create(e:FormEvent<HTMLFormElement>){
    e.preventDefault();if(busy)return;
    const instrument=asset.trim().toUpperCase();
    const price=finite(threshold);
    if(!/^[A-Z0-9._/-]{2,32}$/.test(instrument)||selectedChannels.length===0||
      (needsPrice(kind)&&(price===null||price<=0))){
      setError(true);setNotice("Pick an instrument, at least one channel and, for price alerts, a price above zero.");return;
    }
    setBusy(true);setNotice("");setError(false);
    try{
      const response=await client.POST("/api/v1/platform/alerts",{
        body:{
          asset:instrument,
          alert_type:kind,
          condition:needsPrice(kind)?{value:price}:{},
          channels:selectedChannels,
        },
      });
      if(response.response.ok && response.data && typeof response.data.alert_id==="string"){
        setAsset("");setKind("signal_generated");setThreshold("");setSelectedChannels(["web"]);
        setNotice("Alert created.");onChanged();
      }else{
        setError(true);
        setNotice(response.response.status===403?"Custom alerts aren't on your plan.":response.response.status===401?"Your session expired. Sign in again.":"The alert wasn't created. Try again.");
      }
    }catch{setError(true);setNotice("We couldn't confirm the alert. Refresh to check.");}
    finally{setBusy(false);}
  }

  async function disable(id:string){
    if(!id||deactivating||confirmId!==id)return;
    setDeactivating(id);setNotice("");setError(false);
    try{
      const response=await client.DELETE("/api/v1/platform/alerts/{alert_id}",{params:{path:{alert_id:id}}});
      if(response.response.ok&&response.data&&response.data.disabled===true){
        setConfirmId("");setNotice("Alert turned off.");onChanged();
      }else{setError(true);setNotice("The alert is still on. Try again.");}
    }catch{setError(true);setNotice("We couldn't confirm that. Refresh to check.");}
    finally{setDeactivating("");}
  }

  return <section className="ws-stack">
    <p className="ws-aside">An alert sends you a message when something happens. It doesn&rsquo;t place a trade, and it only arrives on channels you&rsquo;ve connected.</p>
    <div className="ws-cards">
      {items.map((item,i)=>{
        const id=display(item.alert_id,"");
        const rule=record(item.condition);
        const destinations=Array.isArray(item.channels)?item.channels.filter((v):v is string=>typeof v==="string"):[];
        return <article className="ui-card" key={id||i}>
          <p className="ui-eyebrow">{item.active===true?"On":"Off"}</p>
          <h2>{display(item.asset,display(item.instrument_id,"Instrument"))} · {display(item.alert_type).replaceAll("_"," ")}</h2>
          <dl className="ui-kv">
            <div className="ui-kv-row"><dt>Threshold</dt><dd>{item.alert_type==="price_above"||item.alert_type==="price_below"?display(rule.value):"On an event"}</dd></div>
            <div className="ui-kv-row"><dt>Channels</dt><dd>{destinations.length?destinations.join(", "):"Unreported"}</dd></div>
            <div className="ui-kv-row"><dt>Last trigger</dt><dd>{timeLabel(item.last_triggered_at)}</dd></div>
            <div className="ui-kv-row"><dt>Created</dt><dd>{timeLabel(item.created_at)}</dd></div>
          </dl>
          {item.active===true && id && (confirmId===id?
            <div className="ui-confirm" role="group" aria-label="Turn off this alert?">
              <p>It stops sending messages. You can create it again later.</p>
              <button className="ui-btn" type="button" disabled={Boolean(deactivating)} onClick={()=>setConfirmId("")}>Keep rule</button>
              <button className="ui-btn" type="button" disabled={Boolean(deactivating)} onClick={()=>disable(id)}>{deactivating?"Disabling…":"Turn off"}</button>
            </div>:
            <button className="ui-btn" type="button" onClick={()=>setConfirmId(id)}>Turn off</button>)}
        </article>;
      })}
    </div>
    {!items.length&&<div className="ui-empty"><strong>No alerts yet.</strong><p>Create one below. Some plans don&rsquo;t include custom alerts.</p></div>}
    <section className="ui-card">
      <h2>New alert</h2>
      <p>Get a message when a price crosses a level, or when a signal arrives or closes.</p>
      <form className="ui-form" onSubmit={create}>
        <div className="ui-form-grid">
          <label className="ui-field">Instrument / market symbol
            <input className="ui-input" type="text" maxLength={32} minLength={2} required autoComplete="off" value={asset} onChange={e=>setAsset(e.target.value.toUpperCase())} placeholder="BTCUSDT, XAUUSD…"/>
          </label>
          <label className="ui-field">Alert trigger
            <select className="ui-select" value={kind} onChange={e=>setKind(e.target.value as Kind)}>
              {alertKinds.map(([value,label])=><option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          {needsPrice(kind)&&<label className="ui-field">Price threshold
            <input className="ui-input" type="number" min="0.00000001" step="any" inputMode="decimal" required value={threshold} onChange={e=>setThreshold(e.target.value)}/>
          </label>}
        </div>
        <fieldset className="ui-fieldset"><legend>Delivery channels</legend><p>Pick at least one you&rsquo;ve connected.</p><div className="ui-check-row">
          {channels.map(c=><label className="ui-check" key={c}><input type="checkbox" checked={selectedChannels.includes(c)} onChange={e=>setSelectedChannels(current=>e.target.checked?[...current,c]:current.filter(item=>item!==c))}/>{c}</label>)}
        </div></fieldset>
        <button type="submit" className="ui-btn ui-btn--primary" disabled={busy}>{busy?"Creating…":"Create alert"}</button>
        {notice&&<p className={error?"ui-feedback ui-feedback--error":"ui-feedback"} role={error?"alert":"status"}>{notice}</p>}
      </form>
    </section>
  </section>;
}
