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
  return <div className="sr-data-pair"><dt>{label}</dt><dd>{value}</dd></div>;
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
      }catch{if(!cancelled)setState({phase:"error",data:null,message:"Simulation history could not be retrieved."});}
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
    if(risk.trim()){const n=finite(risk);if(n===null||n<0.1||n>10)return feedback("Paper risk must be between 0.1% and 10%.",true);values.risk_pct=n;}
    if(maxPositions.trim()){const n=finite(maxPositions);if(n===null||!Number.isInteger(n)||n<1||n>100)return feedback("Open-position limit must be a whole number from 1 to 100.",true);values.max_open_positions=n;}
    if(minScore.trim()){const n=finite(minScore);if(n===null||n<0||n>100)return feedback("Minimum score must be between 0 and 100.",true);values.min_signal_score=n;}
    if(target) values.target_mode=target;
    if(direction) values.allowed_directions=direction;
    if(marketClasses.length) values.allowed_asset_classes=marketClasses;
    if(!Object.keys(values).length)return feedback("Change at least one simulation setting first.",true);
    setSaving(true);feedback("",false);
    try{
      const response=await client.PUT("/api/v1/platform/paper/settings",{body:values});
      if(response.response.ok&&response.data&&response.data.snapshot){
        feedback("Simulation settings confirmed by the paper service. No broker settings were changed.",false);
        setRisk("");setMaxPositions("");setMinScore("");setTarget("");setDirection("");setMarketClasses([]);
        refresh();
      }else feedback(response.response.status===401?"Session expired. Sign in again.":"No settings change was confirmed. Review the values and retry.",true);
    }catch{feedback("The service could not verify the settings change.",true);}
    finally{setSaving(false);}
  }

  async function applyDestructive(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!action||saving)return;
    const phrase=action==="close"?"CLOSE PAPER POSITIONS":action==="reset"?"RESET PAPER ACCOUNT":"RETRY PAPER SIGNAL";
    if(confirmation!==phrase)return feedback(`Type ${phrase} exactly to confirm the simulation action.`,true);
    const start=finite(resetBalance);
    if(action==="reset"&&(start===null||start<50||start>100_000_000))return feedback("Paper starting balance must be between 50 and 100,000,000 virtual units.",true);
    const reference=signalReference.trim();
    if(action==="retry"&&(reference.length<4||reference.length>64))return feedback("Enter a valid delivered signal reference.",true);
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
        feedback(action==="close"?"Paper close request returned a confirmed snapshot. Inspect the positions to verify each individual closure.":
          action==="reset"?"Paper account reset was confirmed. Prior simulation history may be affected.":
          "Paper retry request was accepted for simulation. This does not guarantee a simulated fill.",false);
        setAction(null);setConfirmation("");setResetBalance("");setSignalReference("");refresh();
      }else feedback("The paper service did not confirm this action. Check account status and retry only after inspection.",true);
    }catch{feedback("The response was not verified. Do not repeat the operation until you have checked your account state.",true);}
    finally{setSaving(false);}
  }

  return <div className="sr-view-stack">
    <section className="sr-data-panel">
      <div className="sr-section-head"><div><p className="sr-overline">Paper only / account-owned</p><h2>Simulation controls and history</h2></div>
        <button type="button" className="sr-secondary-action" onClick={()=>setVersion(v=>v+1)} disabled={saving}>Refresh paper history</button></div>
      <p className="sr-risk-note">Virtual capital only. No live or connected broker trades are issued by this page. Paper outcomes cannot be promoted to broker-confirmed results.</p>
      {state.phase==="loading"&&<p role="status">Retrieving simulation records…</p>}
      {state.phase==="error"&&<div role="alert" className="sr-access-state"><p>{state.message}</p><button type="button" className="sr-secondary-action" onClick={()=>{setState({phase:"loading",data:null,message:""});setVersion(v=>v+1);}}>Retry safely</button></div>}
      {state.phase==="ready"&&<div className="sr-metrics">
        <div className="sr-metric"><span>Paper risk per position</span><strong>{finite(snapshot.risk_pct)===null?"Unavailable":`${numberLabel(snapshot.risk_pct)}%`}</strong><small>Simulated sizing only</small></div>
        <div className="sr-metric"><span>Paper position cap</span><strong>{numberLabel(snapshot.max_open_positions,0)}</strong><small>Enforced by paper service</small></div>
        <div className="sr-metric"><span>Closed paper positions</span><strong>{numberLabel(snapshot.closed_positions,0)}</strong><small>Simulation history</small></div>
        <div className="sr-metric"><span>Paper auto mode</span><strong>{snapshot.auto_trade_enabled===true?"Enabled":snapshot.auto_trade_enabled===false?"Disabled":"Unavailable"}</strong><small>No live trade permission inferred</small></div>
      </div>}
    </section>
    {state.phase==="ready"&&<>
      <div className="sr-grid-two">
        <section className="sr-data-panel"><h2>Simulation performance</h2>
          <p>Derived from the paper service only; not certified live-broker performance.</p>
          <dl><Value label="Simulated realized P&L" value={numberLabel(performance.realized_pnl,2)}/>
            <Value label="Paper closed positions" value={numberLabel(performance.total_trades ?? snapshot.closed_positions,0)}/>
            <Value label="Paper equity" value={numberLabel(snapshot.equity,2)}/>
            <Value label="Target policy" value={display(snapshot.target_mode)}/></dl>
        </section>
        <section className="sr-data-panel"><h2>Current paper policy</h2>
          <dl><Value label="Minimum signal score" value={numberLabel(snapshot.min_signal_score)}/>
            <Value label="Directions" value={display(snapshot.allowed_directions)}/>
            <Value label="Spread estimate (bps)" value={numberLabel(snapshot.spread_bps)}/>
            <Value label="Slippage estimate (bps)" value={numberLabel(snapshot.slippage_bps)}/>
            <Value label="Fees estimate (bps)" value={numberLabel(snapshot.fee_bps)}/></dl>
          <p>Allowed classes: {Array.isArray(snapshot.allowed_asset_classes)?snapshot.allowed_asset_classes.map(String).join(", "):"Unavailable"}</p>
        </section>
      </div>
      <section className="sr-data-panel"><h2>Paper lifecycle records</h2>
        <div className="sr-grid-two">
          <div><h3>Latest paper attempts</h3>
            {activity.length?<div className="sr-history-list">{activity.slice(0,30).map((entry,i)=><div key={i} className="sr-history-row">
              <strong>{display(entry.asset,display(entry.signal_id,"Simulation attempt"))}</strong>
              <span>{display(entry.decision,display(entry.status,"State unavailable"))}</span><small>{timeLabel(entry.created_at ?? entry.attempted_at)}</small>
            </div>)}</div>:<p className="sr-muted">No paper attempts returned.</p>}
          </div>
          <div><h3>Latest closed and skipped positions</h3>
            {closed.length?<div className="sr-history-list">{closed.slice(0,20).map((p,i)=><div key={i} className="sr-history-row">
              <strong>{display(p.asset,"Paper position")}</strong><span>{display(p.status)}</span><small>{timeLabel(p.closed_at)}</small>
            </div>)}</div>:<p className="sr-muted">No closed paper positions returned.</p>}
            <p className="sr-muted">Skipped attempts in response: {skipped.length}. A skip is not a trade.</p>
          </div>
        </div>
      </section>
      <section className="sr-data-panel sr-paper-settings">
        <div><p className="sr-overline">Limited, simulation-only</p><h2>Adjust paper rules</h2></div>
        <p>Only supplied fields are updated. Empty fields preserve your existing settings; the backend validates every limit again.</p>
        <form className="sr-create-form" onSubmit={updateSettings}>
          <div className="sr-form-grid">
            <label>Paper risk per position (%)<input type="number" min="0.1" max="10" step="0.1" value={risk} onChange={e=>setRisk(e.target.value)} placeholder={numberLabel(snapshot.risk_pct)} inputMode="decimal"/></label>
            <label>Maximum open paper positions<input type="number" min="1" max="100" step="1" value={maxPositions} onChange={e=>setMaxPositions(e.target.value)} placeholder={numberLabel(snapshot.max_open_positions,0)}/></label>
            <label>Minimum paper signal score<input type="number" min="0" max="100" step="0.1" value={minScore} onChange={e=>setMinScore(e.target.value)} placeholder={numberLabel(snapshot.min_signal_score)}/></label>
            <label>Paper take-profit target<select value={target} onChange={e=>setTarget(e.target.value)}>
              <option value="">Keep existing ({display(snapshot.target_mode)})</option>
              {targets.map(t=><option key={t} value={t}>{t}</option>)}
            </select></label>
            <label>Allowed paper direction<select value={direction} onChange={e=>setDirection(e.target.value)}>
              <option value="">Keep existing ({display(snapshot.allowed_directions)})</option>
              {directions.map(d=><option key={d} value={d}>{d}</option>)}
            </select></label>
          </div>
          <fieldset className="sr-pref-classes"><legend>Replace entitled paper market classes (optional)</legend>
            <p>If selected, this field replaces your current paper class selection. Leave all unchecked to retain your existing settings.</p>
            <div>{classes.map(c=><label key={c}><input type="checkbox" checked={marketClasses.includes(c)} onChange={e=>setMarketClasses(prev=>e.target.checked?[...prev,c]:prev.filter(x=>x!==c))}/>{c}</label>)}</div>
          </fieldset>
          <button type="submit" className="button" disabled={saving}>{saving?"Saving simulation rules…":"Save paper rules"}</button>
        </form>
      </section>
      <section className="sr-data-panel sr-paper-danger">
        <div><p className="sr-overline">Destructive simulation operations</p><h2>Manage virtual positions and capital</h2></div>
        <p>These affect your simulated account and may be irreversible. They never touch external broker balances.</p>
        <div className="sr-paper-action-row">
          <button type="button" className="sr-secondary-action" onClick={()=>{setAction("close");setConfirmation("");}}>Close open paper positions</button>
          <button type="button" className="sr-secondary-action" onClick={()=>{setAction("reset");setConfirmation("");}}>Reset virtual capital</button>
          <button type="button" className="sr-secondary-action" onClick={()=>{setAction("retry");setConfirmation("");}}>Retry a signal in paper mode</button>
        </div>
        {action&&<form className="sr-create-form sr-paper-confirm" onSubmit={applyDestructive}>
          <h3>{action==="close"?"Close open paper positions":action==="reset"?"Reset your virtual account":"Request a simulated retry"}</h3>
          {action==="reset"&&<label>New starting virtual balance<input required type="number" min="50" max="100000000" step="0.01" inputMode="decimal" value={resetBalance} onChange={e=>setResetBalance(e.target.value)}/></label>}
          {action==="retry"&&<label>Previously delivered signal reference<input required minLength={4} maxLength={64} value={signalReference} onChange={e=>setSignalReference(e.target.value)} autoComplete="off"/></label>}
          <label>Type {action==="close"?"CLOSE PAPER POSITIONS":action==="reset"?"RESET PAPER ACCOUNT":"RETRY PAPER SIGNAL"} to confirm
            <input value={confirmation} onChange={e=>setConfirmation(e.target.value)} required autoComplete="off"/>
          </label>
          <p className="sr-risk-note">The backend independently enforces simulation permissions and safety rules. A request acknowledgement is not a guarantee that every paper position closed.</p>
          <div className="sr-paper-action-row"><button type="submit" className="button" disabled={saving}>{saving?"Submitting…":"Confirm simulation action"}</button>
            <button type="button" className="sr-secondary-action" disabled={saving} onClick={()=>{setAction(null);setConfirmation("");}}>Cancel</button></div>
        </form>}
      </section>
    </>}
    {notice&&<p role={noticeIsError?"alert":"status"} className={noticeIsError?"sr-submit-feedback sr-submit-feedback--error":"sr-submit-feedback"}>{notice}</p>}
  </div>;
}
