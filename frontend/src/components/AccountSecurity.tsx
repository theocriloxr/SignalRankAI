"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
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
      const errors=results.flatMap((r,i)=>r?.response.ok?[]:[["Account information","Device sessions","MFA status"][i]+": "+statusText(r?.response.status)]);
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
      if(r.response.ok&&r.data&&r.data.user){respond("Account profile change confirmed.");setName("");setTimezone("");refresh();}
      else respond(r.response.status===401?"Session expired. Sign in again.":"Profile update was not confirmed.",true);
    }catch{respond("The profile result could not be verified.",true);}
    finally{setBusy(false);}
  }

  async function revoke(){
    if(!revokeId||busy||revokePhrase!=="REVOKE SESSION"||revokeId===data.current)return respond("Confirm the selected non-current session exactly.",true);
    setBusy(true);respond("");
    try{
      const r=await client.DELETE("/api/v1/platform/devices/{session_id}",{params:{path:{session_id:revokeId}}});
      if(r.response.ok&&r.data?.revoked===true){respond("The account service confirmed session revocation.");setRevokeId("");setRevokePhrase("");refresh();}
      else respond("Session revocation was not confirmed. Refresh and retry.",true);
    }catch{respond("Session revocation result could not be verified.",true);}
    finally{setBusy(false);}
  }

  async function signOutAll(){
    if(!logoutAll||busy||logoutPhrase!=="SIGN OUT ALL DEVICES")return respond("Type SIGN OUT ALL DEVICES to confirm.",true);
    setBusy(true);respond("");
    try{
      const r=await client.POST("/api/v1/platform/auth/logout-all");
      if(r.response.ok&&r.data?.logged_out===true){window.location.replace("/login");return;}
      respond("All-device logout was not confirmed; do not assume any session was revoked.",true);
    }catch{respond("All-device logout result could not be verified.",true);}
    finally{setBusy(false);}
  }

  async function startMfa(){
    if(busy||data.mfa?.enabled===true)return;
    setBusy(true);respond("");
    try{
      const r=await client.POST("/api/v1/platform/security/mfa/setup");
      if(r.response.ok&&r.data&&typeof r.data.secret==="string"&&r.data.secret.length>6){
        setEnrollment({secret:r.data.secret,expires:display(r.data.expires_at)});
      }else respond("Authenticator enrollment is unavailable. The account state is unchanged.",true);
    }catch{respond("Could not begin secure authenticator enrollment.",true);}
    finally{setBusy(false);}
  }

  async function finishMfa(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!enrollment||busy||code.trim().length<6)return;
    setBusy(true);respond("");
    try{
      const r=await client.POST("/api/v1/platform/security/mfa/enable",{body:{code:code.trim()}});
      if(r.response.ok&&r.data?.enabled===true){
        setRecoveryCodes(Array.isArray(r.data.recovery_codes)?r.data.recovery_codes.filter((v):v is string=>typeof v==="string"):[]);
        setEnrollment(null);setCode("");respond("MFA enabled. Save the single-use recovery codes securely offline; they will not be shown again.");refresh();
      }else respond("Authenticator code not verified. Check the code and retry.",true);
    }catch{respond("Authenticator enrollment could not be confirmed.",true);}
    finally{setBusy(false);}
  }

  return <section className="sr-view-stack sr-security-center" aria-labelledby="sr-account-security-title">
    <div className="sr-data-panel"><div className="sr-section-head"><div><p className="sr-overline">Identity / Your own account only</p><h2 id="sr-account-security-title">Identity and security</h2></div>
      <button type="button" className="sr-secondary-action" onClick={()=>{setLoading(true);refresh();}}>Refresh security status</button></div>
      <p className="sr-risk-note">Account profile, authenticated sessions and MFA proof are controlled by the backend. This screen never changes broker or prop trading permissions.</p>
      {loading&&<p role="status">Checking account identity and device sessions…</p>}
      {data.errors.length>0&&<div role="alert" className="sr-security-errors">{data.errors.map((e,i)=><p key={i}>{e}</p>)}</div>}
      {data.user&&<dl><div className="sr-data-pair"><dt>Email</dt><dd>{display(data.user.primary_email)}</dd></div>
        <div className="sr-data-pair"><dt>Account name</dt><dd>{display(data.user.display_name)}</dd></div>
        <div className="sr-data-pair"><dt>Access tier</dt><dd>{display(data.user.tier)}</dd></div>
        <div className="sr-data-pair"><dt>Verification</dt><dd>{data.user.email_verified_at?"Verified":"Not verified or not reported"}</dd></div>
        <div className="sr-data-pair"><dt>Timezone</dt><dd>{display(data.user.timezone)}</dd></div></dl>}
      {data.user&&<form className="sr-create-form" onSubmit={saveProfile}>
        <div className="sr-form-grid">
          <label>Update display name<input value={name} onChange={e=>setName(e.target.value)} maxLength={160} placeholder={display(data.user.display_name,"Display name")}/></label>
          <label>Update timezone (IANA)<input value={timezone} onChange={e=>setTimezone(e.target.value)} maxLength={64} placeholder={display(data.user.timezone,"e.g. Africa/Lagos")}/></label>
        </div><button className="button" type="submit" disabled={busy}>Save account profile</button>
      </form>}
      {data.user&&<button className="sr-secondary-action" type="button" disabled={busy} onClick={async()=>{
        setBusy(true);respond("");
        try{const r=await client.POST("/api/v1/platform/auth/email-verification/request");
          if(r.response.ok&&r.data?.accepted===true)respond(r.data.already_verified===true?"Email is already verified.":"Verification email request accepted. Check your inbox without sharing the token.");
          else respond("Verification email was not confirmed.",true);
        }catch{respond("Could not confirm a verification email request.",true);}
        finally{setBusy(false);}
      }}>Request email verification</button>}
    </div>
    <div className="sr-grid-two">
      <section className="sr-data-panel"><h2>Authenticator protection</h2>
        <p>Multi-factor authentication is separate from your SignalRankAI broker policies.</p>
        <dl><div className="sr-data-pair"><dt>MFA status</dt><dd>{data.mfa?.enabled===true?"Enabled":data.mfa?.enabled===false?"Not enabled":"Unavailable"}</dd></div></dl>
        {data.mfa?.enabled===false&&!enrollment&&!recoveryCodes&&<button className="sr-secondary-action" type="button" disabled={busy} onClick={startMfa}>Set up authenticator MFA</button>}
        {enrollment&&<form className="sr-create-form sr-mfa-enrollment" onSubmit={finishMfa}>
          <p className="sr-risk-note">Enter this setup key manually in your authenticator. Keep it private. It is held only in this open page and is not saved in browser storage.</p>
          <code className="sr-mfa-secret">{enrollment.secret}</code><small>Expires: {timeLabel(enrollment.expires)}</small>
          <label>Authenticator&apos;s current code<input value={code} onChange={e=>setCode(e.target.value)} autoComplete="one-time-code" minLength={6} maxLength={32} required inputMode="numeric"/></label>
          <button className="button" type="submit" disabled={busy}>Enable MFA with this code</button>
          <button className="sr-secondary-action" type="button" disabled={busy} onClick={()=>{setEnrollment(null);setCode("");}}>Cancel enrollment</button>
        </form>}
        {recoveryCodes&&<div className="sr-mfa-recovery" role="status"><h3>Recovery codes — shown once</h3>
          <p>Store these codes offline. Do not share them in support messages or screenshots.</p>
          <ul>{recoveryCodes.map((v,i)=><li key={i}><code>{v}</code></li>)}</ul>
          <button className="sr-secondary-action" type="button" onClick={()=>setRecoveryCodes(null)}>I saved these codes — hide them</button>
        </div>}
      </section>
      <section className="sr-data-panel"><h2>Signed-in devices</h2>
        <p>Sessions shown below belong to your account. Each revocation requires confirmation and is enforced on the server.</p>
        <div className="sr-session-list">{data.sessions.map((session,i)=>{
          const id=display(session.session_id,"");
          const current=id===data.current;
          const revoked=Boolean(session.revoked_at);
          return <div className="sr-history-row" key={id||i}>
            <strong>{current?"This device":display(session.device_id,"Unidentified device")}</strong>
            <span>{revoked?"Revoked":current?"Current session":"Other session"}</span>
            <small>Last activity: {timeLabel(session.last_used_at)} · Expires {timeLabel(session.expires_at)}</small>
            {!current&&!revoked&&id&&<button type="button" className="sr-secondary-action" onClick={()=>{setRevokeId(id);setRevokePhrase("");}}>Revoke this session</button>}
          </div>;
        })}</div>
        {data.sessions.length===0&&<p className="sr-muted">No device sessions were returned. This is not proof all sessions are revoked.</p>}
        {revokeId&&<div className="sr-create-form sr-paper-confirm"><h3>Revoke selected session?</h3>
          <label>Type REVOKE SESSION<input value={revokePhrase} onChange={e=>setRevokePhrase(e.target.value)} autoComplete="off"/></label>
          <div className="sr-paper-action-row"><button className="button" type="button" disabled={busy} onClick={revoke}>Confirm revocation</button>
            <button type="button" className="sr-secondary-action" onClick={()=>setRevokeId("")} disabled={busy}>Cancel</button></div>
        </div>}
      </section>
    </div>
    <section className="sr-data-panel sr-broker-freeze"><h2>Sign out everywhere</h2>
      <p>Revoke all sessions for this account, including this browser. Trading controls remain unchanged.</p>
      {!logoutAll?<button type="button" className="sr-secondary-action" onClick={()=>setLogoutAll(true)}>Review all-device sign-out</button>:
      <div className="sr-create-form sr-paper-confirm"><label>Type SIGN OUT ALL DEVICES to confirm
        <input value={logoutPhrase} onChange={e=>setLogoutPhrase(e.target.value)} autoComplete="off"/></label>
        <div className="sr-paper-action-row"><button className="button" type="button" onClick={signOutAll} disabled={busy}>Revoke all sessions</button>
          <button type="button" className="sr-secondary-action" onClick={()=>{setLogoutAll(false);setLogoutPhrase("");}} disabled={busy}>Cancel</button></div></div>}
    </section>
    {feedback&&<p role={error?"alert":"status"} className={error?"sr-submit-feedback sr-submit-feedback--error":"sr-submit-feedback"}>{feedback}</p>}
  </section>;
}
