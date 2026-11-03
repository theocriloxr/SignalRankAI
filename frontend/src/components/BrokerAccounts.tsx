"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { brokerMode, display, moneyLabel, probabilityLabel, record, rows, statusText, timeLabel, type Row } from "../lib/presentation";
import { PropDashboard } from "./PropDashboard";
import { SupportedBrokers } from "./SupportedBrokers";

type Review={policy:Row|null;reconciliation:Row|null;entries:Row[]|null;error:string;ledgerError:string;loading:boolean};
const initial:Review={policy:null,reconciliation:null,entries:null,error:"",ledgerError:"",loading:false};

function Fact({name,value}:{name:string;value:string}) {
  return <div className="ui-kv-row"><dt>{name}</dt><dd>{value}</dd></div>;
}

/** Each broker is resolved by its account-scoped connection_id. No consolidated
 * inferred balance, automatic provider routing or credential disclosure. */
export function BrokerAccounts({data,onChanged}:{data:Row;onChanged:()=>void}){
  const connections=rows(data.connections);
  const [selected,setSelected]=useState("");
  const [version,setVersion]=useState(0);
  const [review,setReview]=useState<Review>(initial);
  const [verifying,setVerifying]=useState(false);
  const [confirmFreeze,setConfirmFreeze]=useState(false);
  const [freezePhrase,setFreezePhrase]=useState("");
  const [freezeReason,setFreezeReason]=useState("");
  const [saving,setSaving]=useState(false);
  const [notice,setNotice]=useState("");
  const [error,setError]=useState(false);

  useEffect(()=>{
    if(!selected)return;
    let cancelled=false;
    async function load(){
      setReview({policy:null,reconciliation:null,entries:null,error:"",ledgerError:"",loading:true});
      const values=await Promise.allSettled([
        client.GET("/api/v1/platform/broker/connections/{connection_id}/policy",{params:{path:{connection_id:selected}}}),
        client.GET("/api/v1/platform/broker/connections/{connection_id}/ledger",{params:{path:{connection_id:selected},query:{limit:100}}}),
      ]);
      if(cancelled)return;
      const [p,l]=values;
      const policyResult=p.status==="fulfilled"?p.value:null;
      const ledgerResult=l.status==="fulfilled"?l.value:null;
      setReview({
        policy:policyResult?.response.ok&&policyResult.data?record(policyResult.data.policy):null,
        reconciliation:policyResult?.response.ok&&policyResult.data?record(policyResult.data.reconciliation):null,
        entries:ledgerResult?.response.ok&&ledgerResult.data?rows(ledgerResult.data.entries):null,
        error:policyResult?.response.ok?"":statusText(policyResult?.response.status),
        ledgerError:ledgerResult?.response.ok?"":statusText(ledgerResult?.response.status),
        loading:false,
      });
    }
    void load();
    return ()=>{cancelled=true};
  },[selected,version]);

  function choose(id:string){
    setSelected(id);setNotice("");setConfirmFreeze(false);setFreezePhrase("");setFreezeReason("");
    if(id===selected)setVersion(v=>v+1);
  }

  async function verify(){
    if(!selected||verifying)return;
    setVerifying(true);setNotice("");setError(false);
    try{
      const result=await client.POST("/api/v1/platform/broker/connections/{connection_id}/verify",{params:{path:{connection_id:selected}}});
      if(result.response.ok&&result.data){
        setNotice("Checked. The status and limits below are up to date.");
        setVersion(v=>v+1);onChanged();
      }else{setError(true);setNotice(result.response.status===401?"Sign in again to inspect this connection.":"We couldn't check this account. The broker may be unreachable.");}
    }catch{setError(true);setNotice("We didn't get an answer from the broker. Try again shortly.");}
    finally{setVerifying(false);}
  }

  async function freeze(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!selected||saving||!confirmFreeze)return;
    const reason=freezeReason.trim();
    if(freezePhrase!=="FREEZE ACCOUNT"||reason.length<8||reason.length>256){
      setError(true);setNotice("Type FREEZE ACCOUNT exactly, and give a reason of at least eight characters.");return;
    }
    setSaving(true);setError(false);setNotice("");
    try{
      const result=await client.POST("/api/v1/platform/broker/connections/{connection_id}/safety-freeze",{
        params:{path:{connection_id:selected}},
        body:{frozen:true,confirm:true,reason},
      });
      if(result.response.ok&&result.data&&result.data.execution_enabled===false&&result.data.policy){
        setNotice("Frozen. No new orders will go to this account.");
        setConfirmFreeze(false);setFreezePhrase("");setFreezeReason("");
        setVersion(v=>v+1);onChanged();
      }else{setError(true);setNotice("The freeze wasn't confirmed. Check the account's status before relying on it.");}
    }catch{setError(true);setNotice("We lost the answer. Check the account's status before trying again.");}
    finally{setSaving(false);}
  }

  const active=connections.find(c=>display(c.connection_id,"")===selected);
  const perm=record(active?.permissions);
  const policy=review.policy;
  const recon=review.reconciliation;
  return <div className="ws-stack">
    <p className="ws-aside">Each linked account has its own limits. Linking an account lets you see it here; it doesn&rsquo;t let us trade on it. Anything the broker hasn&rsquo;t sent us is shown as unavailable.</p>
    <SupportedBrokers/>
    {!connections.length&&<div className="ui-empty"><strong>No broker accounts linked yet.</strong>
      <p>Start with a demo account below.</p></div>}
    {connections.length>0&&<div className="ws-split">
      <nav className="ws-select-list" aria-label="Your broker accounts">
        {connections.map((item,i)=>{
          const id=display(item.connection_id,"");
          const chosen=id===selected;
          return <button type="button" key={id||i} disabled={!id} aria-pressed={chosen}
            className="ws-select-item" onClick={()=>choose(id)}>
            <span className="ui-eyebrow">{display(item.platform)} / {brokerMode(item)}</span>
            <strong>{display(item.account_label,display(item.broker_name,"Broker connection"))}</strong>
            <span>{display(item.account_ref_masked,"Account number hidden")}</span>
            <small>{item.is_default===true?"Default connection · ":""}{display(item.status,"State unavailable")} · {timeLabel(item.verified_at)}</small>
          </button>;
        })}
      </nav>
      <div className="ws-stack">
        {!active&&<section className="ui-card"><h2>Account details</h2>
          <p>Pick an account to see its limits and records.</p></section>}
        {active&&<>
          <section className="ui-card">
            <div className="ui-card-head"><div>
              <h2>{display(active.account_label,display(active.broker_name,"Connected account"))}</h2></div>
              <span className="ui-badge">{brokerMode(active)}</span></div>
            <dl className="ui-kv"><Fact name="Classification" value={display(active.account_classification,"Unverified")}/>
              <Fact name="Connector" value={display(active.connector,display(active.platform))}/>
              <Fact name="Connection status" value={display(active.status)}/>
              <Fact name="Masked account" value={display(active.account_ref_masked)}/>
              <Fact name="Can read balance" value={perm.read===true?"Reported":perm.read===false?"Not confirmed":"Unavailable"}/>
              <Fact name="Order switch" value={active.execution_enabled===true?"On, but orders also need a separate approval":active.execution_enabled===false?"Disabled":"Unknown"}/>
              <Fact name="Last check with the broker" value={timeLabel(active.verified_at)}/>
              <Fact name="Checked at" value={timeLabel(active.last_health_at)}/>
              <Fact name="Broker error" value={display(active.last_error_code,"None reported")}/></dl>
            <div className="ui-actions"><button className="ui-btn" type="button" disabled={verifying} onClick={verify}>{verifying?"Checking…":"Check with the broker"}</button>
              <button className="ui-btn" type="button" onClick={()=>setVersion(v=>v+1)}>Refresh</button></div>
            {notice&&<p className={error?"ui-feedback ui-feedback--error":"ui-feedback"} role={error?"alert":"status"}>{notice}</p>}
          </section>
          {review.loading&&<div className="ui-loading" role="status">Loading…</div>}
          {!review.loading&&<>
            <section className="ui-card"><h2>Limits for this account</h2>
              {review.error&&<p role="alert" className="ui-feedback ui-feedback--error">{review.error}</p>}
              {policy&&<dl className="ui-kv">
                <Fact name="Account mode" value={display(policy.account_mode)}/>
                <Fact name="Can place orders" value={display(policy.execution_permission,"No")}/>
                <Fact name="Status" value={display(policy.status,"Unavailable")}/>
                <Fact name="Risk per trade" value={probabilityLabel(policy.max_risk_per_trade_pct)}/>
                <Fact name="Daily loss cap" value={probabilityLabel(policy.max_daily_loss_pct)}/>
                <Fact name="Maximum drawdown" value={probabilityLabel(policy.max_total_drawdown_pct)}/>
                <Fact name="Frozen" value={policy.frozen===true?"Yes, no new orders":policy.frozen===false?"No":"Unavailable"}/>
              </dl>}
              {!policy&&!review.error&&<p>No limits are set for this account, so it can&rsquo;t place orders.</p>}
              {Object.keys(recon||{}).length>0&&<p className="ui-notice ui-notice--neutral">Balances here come from the broker&rsquo;s last report. Check your broker for the live figure.</p>}
            </section>
            {policy&&<PropDashboard key={selected} connectionId={selected}/>}
            <section className="ui-card"><h2>Account records</h2>
              <p>Deposits, fees and other entries as your broker reported them.</p>
              {review.ledgerError&&<p role="alert" className="ui-feedback ui-feedback--error">{review.ledgerError}</p>}
              {review.entries!==null&&review.entries.length>0&&<div className="ui-table-wrap" tabIndex={0} aria-label="Account records"><table className="ui-table">
                <thead><tr><th>Timestamp</th><th>Entry type</th><th>Amount</th><th>Provider status</th></tr></thead>
                <tbody>{review.entries.map((row,i)=><tr key={display(row.entry_id,String(i))}>
                  <td>{timeLabel(row.created_at ?? row.occurred_at)}</td>
                  <th>{display(row.entry_type)}</th>
                  <td>{moneyLabel(row.amount,row.currency)}</td>
                  <td>{display(row.status,display(row.provenance,"Unverified"))}</td>
                </tr>)}</tbody></table></div>}
              {review.entries!==null&&review.entries.length===0&&<p className="ui-muted">Your broker hasn&rsquo;t sent any records yet.</p>}
            </section>
            <section className="ui-card ui-card--danger">
              <h2>Freeze this account</h2>
              <p>Stops any new orders going to this account. Open positions stay open.</p>
              {!confirmFreeze?<button type="button" className="ui-btn" onClick={()=>setConfirmFreeze(true)}>Freeze account</button>:
                <form onSubmit={freeze} className="ui-form">
                  <label className="ui-field">Reason for freezing<input className="ui-input" minLength={8} maxLength={256} required value={freezeReason} onChange={e=>setFreezeReason(e.target.value)} placeholder="What's wrong? (no passwords)"/></label>
                  <label className="ui-field">Type FREEZE ACCOUNT to confirm<input className="ui-input" autoComplete="off" required value={freezePhrase} onChange={e=>setFreezePhrase(e.target.value)}/></label>
                  <div className="ui-actions">
                    <button className="ui-btn ui-btn--primary" type="submit" disabled={saving}>{saving?"Freezing…":"Confirm account freeze"}</button>
                    <button className="ui-btn" type="button" disabled={saving} onClick={()=>{setConfirmFreeze(false);setFreezePhrase("");setFreezeReason("");}}>Cancel</button>
                  </div>
                </form>}
            </section>
          </>}
        </>}
      </div>
    </div>}
  </div>;
}
