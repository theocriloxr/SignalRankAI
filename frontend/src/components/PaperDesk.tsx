"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, finite, numberLabel, record, rows, statusText, timeLabel, type Row } from "../lib/presentation";

type State = { phase:"loading"|"ready"|"error"; data:Row|null; message:string };
type Action = "close"|"reset"|"retry"|null;
const classes = ["crypto","fx","stock","index","commodity"] as const;
const directions = ["both","long","short"] as const;
const targets = ["TP1","TP2","TP3"] as const;
function Value({label,value}:{label:string;value:string}) {
  return <div className="ui-kv-row"><dt>{label}</dt><dd>{value}</dd></div>;
}

/** Simulation-only controls, backed by the canonical paper trading service.
 * A failed/unknown response is never presented as a completed mutation. */
export function PaperDesk({ onChanged }:{ onChanged:()=>void }) {
  const [version,setVersion]=useState(0);
  const [state,setState]=useState<State>({phase:"loading",data:null,message:""});
  const [action,setAction]=useState<Action>(null);
  const [saving,setSaving]=useState(false);
  const [notice,setNotice]=useState("");
  const [noticeIsError,setNoticeIsError]=useState(false);
  const [risk,setRisk]=useState("");
  const [maxPositions,setMaxPositions]=useState("");
  const [minScore,setMinScore]=useState("");
  const [direction,setDirection]=useState<string>("");
  const [target,setTarget]=useState<string>("");
  const [marketClasses,setMarketClasses]=useState<string[]>([]);
  const [resetBalance,setResetBalance]=useState("");
  const [confirmation,setConfirmation]=useState("");
  const [signalReference,setSignalReference]=useState("");

  useEffect(()=>{
    let cancelled=false;
    async function load(){
      try{
        const response=await client.GET("/api/v1/platform/paper/detail");
        if(cancelled)return;
        if(response.response.ok&&response.data){
          setState({phase:"ready",data:record(response.data),message:""});
        }else setState({phase:"error",data:null,message:statusText(response.response.status)});
      }catch{if(!cancelled)setState({phase:"error",data:null,message:"We couldn't load your paper history."});}
    }
    void load();
    return ()=>{cancelled=true};
  },[version]);

  function feedback(message:string,isError:boolean){
    setNotice(message);setNoticeIsError(isError);
  }
  function refresh(){
    setVersion(v=>v+1);
    onChanged();
  }
  const snapshot=record(state.data?.snapshot);
  const performance=record(state.data?.performance);
  const closed=rows(state.data?.closed_positions);
  const activity=rows(state.data?.activity);
  const skipped=rows(state.data?.skipped_positions);

  async function updateSettings(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(saving||state.phase!=="ready")return;
    const values:{
      risk_pct?:number;max_open_positions?:number;min_signal_score?:number;
      target_mode?:string;allowed_directions?:string;allowed_asset_classes?:string[];
    }={};
    if(risk.trim()){const n=finite(risk);if(n===null||n<0.1||n>10)return feedback("Risk per position must be between 0.1% and 10%.",true);values.risk_pct=n;}
    if(maxPositions.trim()){const n=finite(maxPositions);if(n===null||!Number.isInteger(n)||n<1||n>100)return feedback("The open-position limit must be a whole number from 1 to 100.",true);values.max_open_positions=n;}
    if(minScore.trim()){const n=finite(minScore);if(n===null||n<0||n>100)return feedback("The minimum score must be between 0 and 100.",true);values.min_signal_score=n;}
    if(target) values.target_mode=target;
    if(direction) values.allowed_directions=direction;
    if(marketClasses.length) values.allowed_asset_classes=marketClasses;
    if(!Object.keys(values).length)return feedback("Change at least one setting first.",true);
    setSaving(true);feedback("",false);
    try{
      const response=await client.PUT("/api/v1/platform/paper/settings",{body:values});
      if(response.response.ok&&response.data&&response.data.snapshot){
        feedback("Saved. This only changes your paper account.",false);
        setRisk("");setMaxPositions("");setMinScore("");setTarget("");setDirection("");setMarketClasses([]);
        refresh();
      }else feedback(response.response.status===401?"Session expired. Sign in again.":"Those settings weren't saved. Check the values and try again.",true);
    }catch{feedback("We couldn't confirm the change. Refresh to see what was saved.",true);}
    finally{setSaving(false);}
  }

  async function applyDestructive(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!action||saving)return;
    const phrase=action==="close"?"CLOSE PAPER POSITIONS":action==="reset"?"RESET PAPER ACCOUNT":"RETRY PAPER SIGNAL";
    if(confirmation!==phrase)return feedback(`Type ${phrase} exactly to confirm.`,true);
    const start=finite(resetBalance);
    if(action==="reset"&&(start===null||start<50||start>100_000_000))return feedback("The starting balance must be between 50 and 100,000,000.",true);
    const reference=signalReference.trim();
    if(action==="retry"&&(reference.length<4||reference.length>64))return feedback("Enter the reference of a signal you received.",true);
    setSaving(true);feedback("",false);
    try{
      const response=action==="close"
        ? await client.POST("/api/v1/platform/paper/close-all",{body:{confirm:true,allow_last_mark_fallback:false}})
        : action==="reset"
        ? await client.POST("/api/v1/platform/paper/reset",{body:{confirm:true,starting_balance:start!}})
        : await client.POST("/api/v1/platform/paper/retry",{body:{signal_reference:reference}});
      const accepted=Boolean(response.response.ok&&response.data&&(
        action==="close" ? response.data.snapshot :
        action==="reset" ? response.data.snapshot :
        response.data.accepted===true
      ));
      if(accepted){
        feedback(action==="close"?"Done. Check the list below to see each position closed.":
          action==="reset"?"Your paper account has been reset.":
          "Queued. It fills on paper only if the price reaches the entry.",false);
        setAction(null);setConfirmation("");setResetBalance("");setSignalReference("");refresh();
      }else feedback("That didn't go through. Refresh and check your positions before trying again.",true);
    }catch{feedback("We didn't get an answer. Refresh and check your positions before trying again.",true);}
    finally{setSaving(false);}
  }

  return <div className="ws-stack">
    <section className="ui-card">
      <div className="ui-card-head"><div><h2>How your paper account trades</h2>
        <p className="ui-card-desc">Signals you follow here are filled with pretend money at the prices we see, minus estimated costs.</p></div>
        <button type="button" className="ui-btn ui-btn--sm" onClick={()=>setVersion(v=>v+1)} disabled={saving}>Refresh</button></div>
      {state.phase==="loading"&&<p role="status" className="ui-muted">Loading…</p>}
      {state.phase==="error"&&<div role="alert" className="ui-state"><p>{state.message}</p><button type="button" className="ui-btn" onClick={()=>{setState({phase:"loading",data:null,message:""});setVersion(v=>v+1);}}>Try again</button></div>}
      {state.phase==="ready"&&<div className="ui-stat-grid">
        <div className="ui-stat"><span>Risk per position</span><strong>{finite(snapshot.risk_pct)===null?"Unavailable":`${numberLabel(snapshot.risk_pct)}%`}</strong><small>Of paper equity</small></div>
        <div className="ui-stat"><span>Most positions open at once</span><strong>{numberLabel(snapshot.max_open_positions,0)}</strong></div>
        <div className="ui-stat"><span>Closed so far</span><strong>{numberLabel(snapshot.closed_positions,0)}</strong></div>
        <div className="ui-stat"><span>Follows new signals by itself</span><strong>{snapshot.auto_trade_enabled===true?"Yes":snapshot.auto_trade_enabled===false?"No":"Unavailable"}</strong><small>On paper only</small></div>
      </div>}
    </section>
    {state.phase==="ready"&&<>
      <div className="ws-grid-2">
        <section className="ui-card"><h2>Results on paper</h2>
          <p>Paper fills skip things real brokers do, like requotes and partial fills, so treat these as a best case.</p>
          <dl className="ui-kv"><Value label="Realised profit or loss" value={numberLabel(performance.realized_pnl,2)}/>
            <Value label="Closed positions" value={numberLabel(performance.total_trades ?? snapshot.closed_positions,0)}/>
            <Value label="Equity" value={numberLabel(snapshot.equity,2)}/>
            <Value label="Takes profit at" value={display(snapshot.target_mode)}/></dl>
        </section>
        <section className="ui-card"><h2>Current rules</h2>
          <dl className="ui-kv"><Value label="Minimum signal score" value={numberLabel(snapshot.min_signal_score)}/>
            <Value label="Directions" value={display(snapshot.allowed_directions)}/>
            <Value label="Markets" value={Array.isArray(snapshot.allowed_asset_classes)?snapshot.allowed_asset_classes.map(String).join(", "):"Unavailable"}/>
            <Value label="Assumed spread (basis points)" value={numberLabel(snapshot.spread_bps)}/>
            <Value label="Assumed slippage (basis points)" value={numberLabel(snapshot.slippage_bps)}/>
            <Value label="Assumed fees (basis points)" value={numberLabel(snapshot.fee_bps)}/></dl>
        </section>
      </div>
      <section className="ui-card"><h2>Recent activity</h2>
        <div className="ws-grid-2">
          <div><h3>Signals the desk tried to follow</h3>
            {activity.length?<div className="ui-list">{activity.slice(0,30).map((entry,i)=><div key={i} className="ui-list-row">
              <strong>{display(entry.asset,display(entry.signal_id,"Signal"))}</strong>
              <span>{display(entry.decision,display(entry.status,"State unavailable"))}</span><small>{timeLabel(entry.created_at ?? entry.attempted_at)}</small>
            </div>)}</div>:<p className="ui-muted">Nothing yet.</p>}
          </div>
          <div><h3>Recently closed</h3>
            {closed.length?<div className="ui-list">{closed.slice(0,20).map((p,i)=><div key={i} className="ui-list-row">
              <strong>{display(p.asset,"Paper position")}</strong><span>{display(p.status)}</span><small>{timeLabel(p.closed_at)}</small>
            </div>)}</div>:<p className="ui-muted">Nothing closed yet.</p>}
            {skipped.length>0&&<p className="ui-muted">{skipped.length} skipped without opening a position.</p>}
          </div>
        </div>
      </section>
      <section className="ui-card">
        <div><h2>Change the rules</h2></div>
        <p>Fill in only what you want to change. Blank fields keep their current value.</p>
        <form className="ui-form" onSubmit={updateSettings}>
          <div className="ui-form-grid">
            <label className="ui-field">Risk per position (%)<input className="ui-input" type="number" min="0.1" max="10" step="0.1" value={risk} onChange={e=>setRisk(e.target.value)} placeholder={numberLabel(snapshot.risk_pct)} inputMode="decimal"/></label>
            <label className="ui-field">Most positions open at once<input className="ui-input" type="number" min="1" max="100" step="1" value={maxPositions} onChange={e=>setMaxPositions(e.target.value)} placeholder={numberLabel(snapshot.max_open_positions,0)}/></label>
            <label className="ui-field">Minimum signal score<input className="ui-input" type="number" min="0" max="100" step="0.1" value={minScore} onChange={e=>setMinScore(e.target.value)} placeholder={numberLabel(snapshot.min_signal_score)}/></label>
            <label className="ui-field">Take profit at<select className="ui-select" value={target} onChange={e=>setTarget(e.target.value)}>
              <option value="">Keep {display(snapshot.target_mode)}</option>
              {targets.map(t=><option key={t} value={t}>{t}</option>)}
            </select></label>
            <label className="ui-field">Directions<select className="ui-select" value={direction} onChange={e=>setDirection(e.target.value)}>
              <option value="">Keep {display(snapshot.allowed_directions)}</option>
              {directions.map(d=><option key={d} value={d}>{d}</option>)}
            </select></label>
          </div>
          <fieldset className="ui-fieldset"><legend>Markets (optional)</legend>
            <p>Ticking any of these replaces your current list. Leave them all unticked to keep it.</p>
            <div className="ui-check-row">{classes.map(c=><label className="ui-check" key={c}><input type="checkbox" checked={marketClasses.includes(c)} onChange={e=>setMarketClasses(prev=>e.target.checked?[...prev,c]:prev.filter(x=>x!==c))}/>{c}</label>)}</div>
          </fieldset>
          <button type="submit" className="ui-btn ui-btn--primary" disabled={saving}>{saving?"Saving…":"Save rules"}</button>
        </form>
      </section>
      <section className="ui-card ui-card--danger">
        <div><h2>Start over</h2></div>
        <p>These change your paper account and can&rsquo;t be undone. Broker accounts aren&rsquo;t affected.</p>
        <div className="ui-actions">
          <button type="button" className="ui-btn" onClick={()=>{setAction("close");setConfirmation("");}}>Close all paper positions</button>
          <button type="button" className="ui-btn" onClick={()=>{setAction("reset");setConfirmation("");}}>Reset the paper balance</button>
          <button type="button" className="ui-btn" onClick={()=>{setAction("retry");setConfirmation("");}}>Follow a past signal on paper</button>
        </div>
        {action&&<form className="ui-confirm" onSubmit={applyDestructive}>
          <h3>{action==="close"?"Close all paper positions":action==="reset"?"Reset your paper balance":"Follow a past signal on paper"}</h3>
          {action==="reset"&&<label className="ui-field">New starting balance<input className="ui-input" required type="number" min="50" max="100000000" step="0.01" inputMode="decimal" value={resetBalance} onChange={e=>setResetBalance(e.target.value)}/></label>}
          {action==="retry"&&<label className="ui-field">Signal reference<input className="ui-input" required minLength={4} maxLength={64} value={signalReference} onChange={e=>setSignalReference(e.target.value)} autoComplete="off"/></label>}
          <label className="ui-field">Type {action==="close"?"CLOSE PAPER POSITIONS":action==="reset"?"RESET PAPER ACCOUNT":"RETRY PAPER SIGNAL"} to confirm
            <input className="ui-input" value={confirmation} onChange={e=>setConfirmation(e.target.value)} required autoComplete="off"/>
          </label>
                    <div className="ui-actions"><button type="submit" className="ui-btn ui-btn--primary" disabled={saving}>{saving?"Working…":"Confirm"}</button>
            <button type="button" className="ui-btn" disabled={saving} onClick={()=>{setAction(null);setConfirmation("");}}>Cancel</button></div>
        </form>}
      </section>
    </>}
    {notice&&<p role={noticeIsError?"alert":"status"} className={noticeIsError?"ui-feedback ui-feedback--error":"ui-feedback"}>{notice}</p>}
  </div>;
}
