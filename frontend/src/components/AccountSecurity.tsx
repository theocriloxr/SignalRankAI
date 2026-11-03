"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { TelegramConnection } from "./TelegramConnection";
import { display, record, rows, statusText, timeLabel, type Row } from "../lib/presentation";

type Loaded={user:Row|null;sessions:Row[];current:string;mfa:Row|null;errors:string[]};
const empty:Loaded={user:null,sessions:[],current:"",mfa:null,errors:[]};

export function AccountSecurity({onChanged}:{onChanged:()=>void}){
  const [data,setData]=useState<Loaded>(empty);
  const [loading,setLoading]=useState(true);
  const [version,setVersion]=useState(0);
  const [busy,setBusy]=useState(false);
  const [name,setName]=useState("");
  const [timezone,setTimezone]=useState("");
  const [feedback,setFeedback]=useState("");
  const [error,setError]=useState(false);
  const [revokeId,setRevokeId]=useState("");
  const [revokePhrase,setRevokePhrase]=useState("");
  const [logoutAll,setLogoutAll]=useState(false);
  const [logoutPhrase,setLogoutPhrase]=useState("");
  const [enrollment,setEnrollment]=useState<{secret:string;expires:string}|null>(null);
  const [code,setCode]=useState("");
  const [recoveryCodes,setRecoveryCodes]=useState<string[]|null>(null);

  useEffect(()=>{
    let cancelled=false;
    async function load(){
      const responses=await Promise.allSettled([
        client.GET("/api/v1/platform/me"),
        client.GET("/api/v1/platform/devices"),
        client.GET("/api/v1/platform/security/mfa")
      ]);
      if(cancelled)return;
      const results=responses.map(r=>r.status==="fulfilled"?r.value:null);
      const errors=results.flatMap((r,i)=>r?.response.ok?[]:[["Account information","Device sessions","Status"][i]+": "+statusText(r?.response.status)]);
      const user=results[0]?.response.ok?record(results[0]?.data?.user):null;
      const devices=results[1]?.response.ok?record(results[1]?.data):{};
      const mfa=results[2]?.response.ok?record(results[2]?.data):null;
      setData({user,sessions:rows(devices.sessions),current:display(devices.current_session_id,""),mfa,errors});
      setLoading(false);
    }
    void load();
    return ()=>{cancelled=true;};
  },[version]);

  function respond(text:string,failed=false){setFeedback(text);setError(failed);}
  function refresh(){setVersion(v=>v+1);onChanged();}

  async function saveProfile(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(busy||!data.user)return;
    const body:{display_name?:string;timezone?:string}={};
    const proposedName=name.trim(),proposedTimezone=timezone.trim();
    if(proposedName){if(proposedName.length>160)return respond("Name must be 160 characters or fewer.",true);body.display_name=proposedName;}
    if(proposedTimezone){if(proposedTimezone.length>64)return respond("Timezone must be 64 characters or fewer.",true);body.timezone=proposedTimezone;}
    if(!Object.keys(body).length)return respond("Enter a changed name or timezone first.",true);
    setBusy(true);respond("");
    try{
      const r=await client.PATCH("/api/v1/platform/profile",{body});
      if(r.response.ok&&r.data&&r.data.user){respond("Saved.");setName("");setTimezone("");refresh();}
      else respond(r.response.status===401?"Session expired. Sign in again.":"That didn't save. Try again.",true);
    }catch{respond("We couldn't confirm the change. Refresh to check.",true);}
    finally{setBusy(false);}
  }

  async function revoke(){
    if(!revokeId||busy||revokePhrase!=="REVOKE SESSION"||revokeId===data.current)return respond("Type REVOKE SESSION to confirm.",true);
    setBusy(true);respond("");
    try{
      const r=await client.DELETE("/api/v1/platform/devices/{session_id}",{params:{path:{session_id:revokeId}}});
      if(r.response.ok&&r.data?.revoked===true){respond("Signed out on that device.");setRevokeId("");setRevokePhrase("");refresh();}
      else respond("That device is still signed in. Try again.",true);
    }catch{respond("We couldn't confirm it. Refresh to check.",true);}
    finally{setBusy(false);}
  }

  async function signOutAll(){
    if(!logoutAll||busy||logoutPhrase!=="SIGN OUT ALL DEVICES")return respond("Type SIGN OUT ALL DEVICES to confirm.",true);
    setBusy(true);respond("");
    try{
      const r=await client.POST("/api/v1/platform/auth/logout-all");
      if(r.response.ok&&r.data?.logged_out===true){window.location.replace("/login");return;}
      respond("That didn't go through. Your devices may still be signed in.",true);
    }catch{respond("We couldn't confirm it. Refresh to check.",true);}
    finally{setBusy(false);}
  }

  async function startMfa(){
    if(busy||data.mfa?.enabled===true)return;
    setBusy(true);respond("");
    try{
      const r=await client.POST("/api/v1/platform/security/mfa/setup");
      if(r.response.ok&&r.data&&typeof r.data.secret==="string"&&r.data.secret.length>6){
        setEnrollment({secret:r.data.secret,expires:display(r.data.expires_at)});
      }else respond("Authenticator setup isn't available right now. Nothing changed.",true);
    }catch{respond("We couldn't start authenticator setup. Try again.",true);}
    finally{setBusy(false);}
  }

  async function finishMfa(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!enrollment||busy||code.trim().length<6)return;
    setBusy(true);respond("");
    try{
      const r=await client.POST("/api/v1/platform/security/mfa/enable",{body:{code:code.trim()}});
      if(r.response.ok&&r.data?.enabled===true){
        setRecoveryCodes(Array.isArray(r.data.recovery_codes)?r.data.recovery_codes.filter((v):v is string=>typeof v==="string"):[]);
        setEnrollment(null);setCode("");setData(previous=>({...previous,mfa:{...previous.mfa,enabled:true}}));respond("Two-step sign-in is on. Save the recovery codes below somewhere safe; we won't show them again.");
      }else respond("That code didn't work. Check it and try again.",true);
    }catch{respond("We couldn't confirm the setup. Try again.",true);}
    finally{setBusy(false);}
  }

  return <section className="ws-stack" aria-labelledby="sr-account-security-title">
    <div className="ui-card"><div className="ui-card-head"><div><h2 id="sr-account-security-title">Sign-in and security</h2></div>
      <button type="button" className="ui-btn" onClick={()=>{setLoading(true);refresh();}}>Refresh</button></div>
      <p className="ws-aside">Your name, the devices you&rsquo;re signed in on, and two-step sign-in.</p>
      {loading&&<p role="status">Loading…</p>}
      {data.errors.length>0&&<div role="alert" className="ui-notice ui-notice--danger">{data.errors.map((e,i)=><p key={i}>{e}</p>)}</div>}
      {data.user&&<dl className="ui-kv"><div className="ui-kv-row"><dt>Email</dt><dd>{display(data.user.primary_email)}</dd></div>
        <div className="ui-kv-row"><dt>Account name</dt><dd>{display(data.user.display_name)}</dd></div>
        <div className="ui-kv-row"><dt>Plan</dt><dd>{display(data.user.tier)}</dd></div>
        <div className="ui-kv-row"><dt>Verification</dt><dd>{data.user.email_verified_at?"Verified":"Not verified"}</dd></div>
        <div className="ui-kv-row"><dt>Timezone</dt><dd>{display(data.user.timezone)}</dd></div></dl>}
      {data.user&&<form className="ui-form" onSubmit={saveProfile}>
        <div className="ui-form-grid">
          <label className="ui-field">Update display name<input className="ui-input" value={name} onChange={e=>setName(e.target.value)} maxLength={160} placeholder={display(data.user.display_name,"Display name")}/></label>
          <label className="ui-field">Timezone (for example Africa/Lagos)<input className="ui-input" value={timezone} onChange={e=>setTimezone(e.target.value)} maxLength={64} placeholder={display(data.user.timezone,"e.g. Africa/Lagos")}/></label>
        </div><button className="ui-btn ui-btn--primary" type="submit" disabled={busy}>Save</button>
      </form>}
      {data.user&&!data.user.email_verified_at&&<button className="ui-btn" type="button" disabled={busy} onClick={async()=>{
        setBusy(true);respond("");
        try{const r=await client.POST("/api/v1/platform/auth/email-verification/request");
          if(r.response.ok&&r.data?.accepted===true)respond(r.data.already_verified===true?"Email is already verified.":"Sent. Check your inbox.");
          else respond("The email didn't send. Try again.",true);
        }catch{respond("We couldn't confirm it. Try again.",true);}
        finally{setBusy(false);}
      }}>Send verification email</button>}
    </div>
    {data.user&&<TelegramConnection user={data.user} onRefresh={refresh}/>}
    <div className="ws-grid-2">
      <section className="ui-card"><h2>Two-step sign-in</h2>
        <p>Ask for a code from an authenticator app when you sign in.</p>
        <dl className="ui-kv"><div className="ui-kv-row"><dt>Status</dt><dd>{data.mfa?.enabled===true?"Enabled":data.mfa?.enabled===false?"Not enabled":"Unavailable"}</dd></div></dl>
        {data.mfa?.enabled===false&&!enrollment&&!recoveryCodes&&<button className="ui-btn" type="button" disabled={busy} onClick={startMfa}>Set up an authenticator</button>}
        {enrollment&&<form className="ui-confirm" onSubmit={finishMfa}>
          <p className="ui-notice ui-notice--neutral">Type this key into your authenticator app. Keep it private; it disappears when you leave this page.</p>
          <code className="ui-secret">{enrollment.secret}</code><small>Expires: {timeLabel(enrollment.expires)}</small>
          <label className="ui-field">Code from the app<input className="ui-input" value={code} onChange={e=>setCode(e.target.value)} autoComplete="one-time-code" minLength={6} maxLength={32} required inputMode="numeric"/></label>
          <button className="ui-btn ui-btn--primary" type="submit" disabled={busy}>Turn on</button>
          <button className="ui-btn" type="button" disabled={busy} onClick={()=>{setEnrollment(null);setCode("");}}>Cancel</button>
        </form>}
        {recoveryCodes&&<div className="ui-confirm" role="status"><h3>Recovery codes (shown once)</h3>
          <p>Keep them offline. Don&rsquo;t send them to anyone, including us.</p>
          <ul>{recoveryCodes.map((v,i)=><li key={i}><code>{v}</code></li>)}</ul>
          <button className="ui-btn" type="button" onClick={()=>{setRecoveryCodes(null);refresh();}}>I&rsquo;ve saved them</button>
        </div>}
      </section>
      <section className="ui-card"><h2>Where you&rsquo;re signed in</h2>
        <p>Sign out any device you don&rsquo;t recognise.</p>
        <div className="ui-list">{data.sessions.map((session,i)=>{
          const id=display(session.session_id,"");
          const current=id===data.current;
          const revoked=Boolean(session.revoked_at);
          return <div className="ui-list-row" key={id||i}>
            <strong>{current?"This device":display(session.device_id,"Unknown device")}</strong>
            <span>{revoked?"Signed out":current?"Current":"Active"}</span>
            <small>Last activity: {timeLabel(session.last_used_at)} · Expires {timeLabel(session.expires_at)}</small>
            {!current&&!revoked&&id&&<button type="button" className="ui-btn" onClick={()=>{setRevokeId(id);setRevokePhrase("");}}>Sign out this device</button>}
          </div>;
        })}</div>
        {data.sessions.length===0&&<p className="ui-muted">We couldn&rsquo;t list your devices.</p>}
        {revokeId&&<div className="ui-confirm"><h3>Sign out that device?</h3>
          <label className="ui-field">Type REVOKE SESSION<input className="ui-input" value={revokePhrase} onChange={e=>setRevokePhrase(e.target.value)} autoComplete="off"/></label>
          <div className="ui-actions"><button className="ui-btn ui-btn--primary" type="button" disabled={busy} onClick={revoke}>Sign out device</button>
            <button type="button" className="ui-btn" onClick={()=>setRevokeId("")} disabled={busy}>Cancel</button></div>
        </div>}
      </section>
    </div>
    <section className="ui-card ui-card--danger"><h2>Sign out everywhere</h2>
      <p>Signs out every device, including this one.</p>
      {!logoutAll?<button type="button" className="ui-btn" onClick={()=>setLogoutAll(true)}>Sign out everywhere…</button>:
      <div className="ui-confirm"><label className="ui-field">Type SIGN OUT ALL DEVICES to confirm
        <input className="ui-input" value={logoutPhrase} onChange={e=>setLogoutPhrase(e.target.value)} autoComplete="off"/></label>
        <div className="ui-actions"><button className="ui-btn ui-btn--primary" type="button" onClick={signOutAll} disabled={busy}>Sign out everywhere</button>
          <button type="button" className="ui-btn" onClick={()=>{setLogoutAll(false);setLogoutPhrase("");}} disabled={busy}>Cancel</button></div></div>}
    </section>
    {feedback&&<p role={error?"alert":"status"} className={error?"ui-feedback ui-feedback--error":"ui-feedback"}>{feedback}</p>}
  </section>;
}
