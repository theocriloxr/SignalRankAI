"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { brokerMode, display, moneyLabel, probabilityLabel, numberLabel, record, rows, statusText, timeLabel, type Row } from "../lib/presentation";

type Review={policy:Row|null;reconciliation:Row|null;entries:Row[]|null;error:string;ledgerError:string;loading:boolean};
const initial:Review={policy:null,reconciliation:null,entries:null,error:"",ledgerError:"",loading:false};

function Fact({name,value}:{name:string;value:string}) {
  return <div className="sr-data-pair"><dt>{name}</dt><dd>{value}</dd></div>;
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
        setNotice("The broker verification request returned an account-owned result. Read the refreshed account status and policy before making trading decisions.");
        setVersion(v=>v+1);onChanged();
      }else{setError(true);setNotice(result.response.status===401?"Sign in again to inspect this connection.":"Read-only broker verification was not confirmed. Provider may be unavailable.");}
    }catch{setError(true);setNotice("The provider verification result was unavailable. No readiness has been assumed.");}
    finally{setVerifying(false);}
  }

  async function freeze(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!selected||saving||!confirmFreeze)return;
    const reason=freezeReason.trim();
    if(freezePhrase!=="FREEZE ACCOUNT"||reason.length<8||reason.length>256){
      setError(true);setNotice("Type FREEZE ACCOUNT exactly and provide a reason of at least eight characters.");return;
    }
    setSaving(true);setError(false);setNotice("");
    try{
      const result=await client.POST("/api/v1/platform/broker/connections/{connection_id}/safety-freeze",{
        params:{path:{connection_id:selected}},
        body:{frozen:true,confirm:true,reason},
      });
      if(result.response.ok&&result.data&&result.data.execution_enabled===false&&result.data.policy){
        setNotice("The account service confirmed the safety freeze. New broker execution for this account is disabled.");
        setConfirmFreeze(false);setFreezePhrase("");setFreezeReason("");
        setVersion(v=>v+1);onChanged();
      }else{setError(true);setNotice("Freeze confirmation was not received. Do not assume this account has been frozen; verify status.");}
    }catch{setError(true);setNotice("The freeze response was interrupted. Verify the broker account policy before retrying.");}
    finally{setSaving(false);}
  }

  const active=connections.find(c=>display(c.connection_id,"")===selected);
  const perm=record(active?.permissions);
  const policy=review.policy;
  const recon=review.reconciliation;
  return <div className="sr-view-stack">
    <p className="sr-risk-note">Every account is evaluated independently. A connected broker is NOT approval for live, prop or automated execution. Missing provider margin, currency, permission and ledger data remain unavailable.</p>
    {!connections.length&&<div className="sr-empty"><strong>No entitled broker connections returned.</strong>
      <p>Connect a demo account in the certified provider workflow before attempting any live integration. No account balance has been assumed.</p></div>}
    {connections.length>0&&<div className="sr-broker-layout">
      <nav className="sr-broker-account-list" aria-label="Your connected broker accounts">
        {connections.map((item,i)=>{
          const id=display(item.connection_id,"");
          const chosen=id===selected;
          return <button type="button" key={id||i} disabled={!id} aria-pressed={chosen}
            className={chosen?"sr-broker-account active":"sr-broker-account"} onClick={()=>choose(id)}>
            <span className="sr-overline">{display(item.platform)} / {brokerMode(item)}</span>
            <strong>{display(item.account_label,display(item.broker_name,"Broker connection"))}</strong>
            <span>{display(item.account_ref_masked,"Account reference masked")}</span>
            <small>{item.is_default===true?"Default connection · ":""}{display(item.status,"State unavailable")} · {timeLabel(item.verified_at)}</small>
          </button>;
        })}
      </nav>
      <div className="sr-view-stack sr-broker-details">
        {!active&&<section className="sr-data-panel"><h2>Inspect a broker account</h2>
          <p>Select a connection to inspect its independent policy, reconciliation and ledger. No account is selected automatically for orders.</p></section>}
        {active&&<>
          <section className="sr-data-panel">
            <div className="sr-section-head"><div><p className="sr-overline">Account-scoped broker evidence</p>
              <h2>{display(active.account_label,display(active.broker_name,"Connected account"))}</h2></div>
              <span className="sr-state">{brokerMode(active)}</span></div>
            <dl><Fact name="Classification" value={display(active.account_classification,"Unverified")}/>
              <Fact name="Connector" value={display(active.connector,display(active.platform))}/>
              <Fact name="Connection status" value={display(active.status)}/>
              <Fact name="Masked account" value={display(active.account_ref_masked)}/>
              <Fact name="Read permission" value={perm.read===true?"Reported":perm.read===false?"Not reported enabled":"Unavailable"}/>
              <Fact name="Execution toggle" value={active.execution_enabled===true?"Enabled flag — requires separate release certification":active.execution_enabled===false?"Disabled":"Unknown"}/>
              <Fact name="Provider verification" value={timeLabel(active.verified_at)}/>
              <Fact name="Health last checked" value={timeLabel(active.last_health_at)}/>
              <Fact name="Provider error" value={display(active.last_error_code,"None reported")}/></dl>
            <div className="sr-paper-action-row"><button className="sr-secondary-action" type="button" disabled={verifying} onClick={verify}>{verifying?"Verifying provider…":"Run read-only verification"}</button>
              <button className="sr-secondary-action" type="button" onClick={()=>setVersion(v=>v+1)}>Refresh policy and ledger</button></div>
            {notice&&<p className={error?"sr-submit-feedback sr-submit-feedback--error":"sr-submit-feedback"} role={error?"alert":"status"}>{notice}</p>}
          </section>
          {review.loading&&<div className="sr-loading" role="status">Retrieving account policy and broker-confirmed ledger…</div>}
          {!review.loading&&<>
            <section className="sr-data-panel"><h2>Independent account risk policy</h2>
              {review.error&&<p role="alert" className="sr-submit-feedback sr-submit-feedback--error">{review.error}</p>}
              {policy&&<dl>
                <Fact name="Account mode" value={display(policy.account_mode)}/>
                <Fact name="Execution permission" value={display(policy.execution_permission,"Not authorized")}/>
                <Fact name="Policy status" value={display(policy.status,"Unavailable")}/>
                <Fact name="Risk per trade" value={probabilityLabel(policy.max_risk_per_trade_pct)}/>
                <Fact name="Daily loss cap" value={probabilityLabel(policy.max_daily_loss_pct)}/>
                <Fact name="Maximum drawdown" value={probabilityLabel(policy.max_total_drawdown_pct)}/>
                <Fact name="Frozen" value={policy.frozen===true?"Yes — no new execution":policy.frozen===false?"No freeze reported":"Unavailable"}/>
              </dl>}
              {!policy&&!review.error&&<p>Policy data was not provided. Execution approval cannot be assumed.</p>}
              {Object.keys(recon||{}).length>0&&<p className="sr-risk-note">Reconciliation is returned separately by the canonical account service. It must be verified against the provider before treating values as authoritative.</p>}
            </section>
            <section className="sr-data-panel"><h2>Broker ledger evidence</h2>
              <p>Only the backend&apos;s provider-attributed ledger rows are shown. Missing deposits, fees, funding or swap values are never inferred.</p>
              {review.ledgerError&&<p role="alert" className="sr-submit-feedback sr-submit-feedback--error">{review.ledgerError}</p>}
              {review.entries!==null&&review.entries.length>0&&<div className="sr-table-scroll" tabIndex={0} aria-label="Scrollable account-specific broker ledger"><table>
                <thead><tr><th>Timestamp</th><th>Entry type</th><th>Amount</th><th>Provider status</th></tr></thead>
                <tbody>{review.entries.map((row,i)=><tr key={display(row.entry_id,String(i))}>
                  <td>{timeLabel(row.created_at ?? row.occurred_at)}</td>
                  <th>{display(row.entry_type)}</th>
                  <td>{moneyLabel(row.amount,row.currency)}</td>
                  <td>{display(row.status,display(row.provenance,"Unverified"))}</td>
                </tr>)}</tbody></table></div>}
              {review.entries!==null&&review.entries.length===0&&<p className="sr-muted">No broker-confirmed ledger records were returned. This does not imply a zero balance.</p>}
            </section>
            <section className="sr-data-panel sr-broker-freeze"><p className="sr-overline">Safety-only / No execution activation</p>
              <h2>Freeze this broker account</h2>
              <p>Use this to suspend new broker execution for this connection. Freezing does not close any existing broker position.</p>
              {!confirmFreeze?<button type="button" className="sr-secondary-action" onClick={()=>setConfirmFreeze(true)}>Begin safety freeze</button>:
                <form onSubmit={freeze} className="sr-create-form">
                  <label>Reason for freezing<input minLength={8} maxLength={256} required value={freezeReason} onChange={e=>setFreezeReason(e.target.value)} placeholder="Describe the risk concern (no credentials)"/></label>
                  <label>Type FREEZE ACCOUNT to confirm<input autoComplete="off" required value={freezePhrase} onChange={e=>setFreezePhrase(e.target.value)}/></label>
                  <div className="sr-paper-action-row">
                    <button className="button" type="submit" disabled={saving}>{saving?"Freezing…":"Confirm account freeze"}</button>
                    <button className="sr-secondary-action" type="button" disabled={saving} onClick={()=>{setConfirmFreeze(false);setFreezePhrase("");setFreezeReason("");}}>Cancel</button>
                  </div>
                </form>}
            </section>
          </>}
        </>}
      </div>
    </div>}
  </div>;
}
