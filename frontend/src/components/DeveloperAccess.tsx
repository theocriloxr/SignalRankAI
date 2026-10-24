"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, record, rows, statusText, timeLabel, type Row } from "../lib/presentation";

// Mirrors the server allowlist; the API rejects anything else.
const keyScopes = [
  ["signals:read","Delivered signals"],["instruments:read","Instrument directory"],
  ["portfolio:read","Portfolio summary"],["paper:read","Paper trading"],
  ["journal:read","Journal"],["organization:read","Organization"],
] as const;
const webhookEvents = [["signal.generated","Signal generated"],["signal.closed","Signal closed"]] as const;
type Secret = {label:string;value:string};
type Loaded = {keys:Row[]|null;hooks:Row[]|null;keyStatus:number;hookStatus:number};

function failure(status:number, fallback:string){
  if(status===401)return "Your session expired. Sign in again.";
  if(status===403)return "This needs a plan that includes developer access, or a fresh sign-in for credential changes. Sign out and back in, then retry within 15 minutes.";
  if(status===422)return "The service rejected these details. Check the values and retry.";
  if(status===503)return "Signing-secret encryption is not configured on the server, so webhooks cannot be created yet.";
  return fallback;
}

export function DeveloperAccess(){
  const [data,setData]=useState<Loaded>({keys:null,hooks:null,keyStatus:0,hookStatus:0});
  const [loading,setLoading]=useState(true);
  const [version,setVersion]=useState(0);
  const [busy,setBusy]=useState(false);
  const [keyName,setKeyName]=useState("");
  const [scopes,setScopes]=useState<string[]>(["signals:read"]);
  const [days,setDays]=useState("90");
  const [hookUrl,setHookUrl]=useState("");
  const [events,setEvents]=useState<string[]>(["signal.generated","signal.closed"]);
  const [confirm,setConfirm]=useState("");
  const [secret,setSecret]=useState<Secret|null>(null);
  const [notice,setNotice]=useState("");
  const [error,setError]=useState(false);

  useEffect(()=>{
    let cancelled=false;
    async function load(){
      const [keys,hooks]=await Promise.allSettled([client.GET("/api/v1/platform/api-keys"),client.GET("/api/v1/platform/webhooks")]);
      if(cancelled)return;
      const k=keys.status==="fulfilled"?keys.value:null, h=hooks.status==="fulfilled"?hooks.value:null;
      setData({
        keys:k?.response.ok?rows(record(k.data).api_keys):null,
        hooks:h?.response.ok?rows(record(h.data).webhooks):null,
        keyStatus:k?.response.status??0,hookStatus:h?.response.status??0,
      });
      setLoading(false);
    }
    void load();
    return ()=>{cancelled=true;};
  },[version]);

  function respond(text:string,failed=false){setNotice(text);setError(failed);}

  async function createKey(e:FormEvent<HTMLFormElement>){
    e.preventDefault();if(busy)return;
    const name=keyName.trim(), expiry=Number(days);
    if(!name||name.length>120||!scopes.length||!Number.isInteger(expiry)||expiry<1||expiry>3650)
      return respond("Give the key a name, at least one scope and an expiry between 1 and 3650 days.",true);
    setBusy(true);respond("");setSecret(null);
    try{
      const r=await client.POST("/api/v1/platform/api-keys",{body:{name,scopes,expires_in_days:expiry}});
      const value=display(record(r.data).api_key,"");
      if(r.response.ok&&value){
        setSecret({label:`API key “${name}”`,value});setKeyName("");setScopes(["signals:read"]);setDays("90");
        respond("Key created. Copy it now: it is shown once and is not stored in this browser.");setVersion(v=>v+1);
      }else respond(failure(r.response.status,"The service did not confirm key creation."),true);
    }catch{respond("Key creation could not be confirmed. Retry later.",true);}
    finally{setBusy(false);}
  }

  async function revokeKey(id:string){
    if(busy||confirm!=="key:"+id)return;
    setBusy(true);respond("");
    try{
      const r=await client.DELETE("/api/v1/platform/api-keys/{key_id}",{params:{path:{key_id:id}}});
      if(r.response.ok&&record(r.data).revoked===true){setConfirm("");respond("The service confirmed this key is revoked.");setVersion(v=>v+1);}
      else respond(failure(r.response.status,"Revocation could not be confirmed. Refresh and retry."),true);
    }catch{respond("Revocation could not be verified. Retry.",true);}
    finally{setBusy(false);}
  }

  async function createHook(e:FormEvent<HTMLFormElement>){
    e.preventDefault();if(busy)return;
    const url=hookUrl.trim();
    let parsed:URL|null=null;
    try{parsed=new URL(url);}catch{parsed=null;}
    if(!parsed||parsed.protocol!=="https:"||url.length>2048||!events.length)
      return respond("Use a public https:// endpoint and choose at least one event.",true);
    setBusy(true);respond("");setSecret(null);
    try{
      const r=await client.POST("/api/v1/platform/webhooks",{body:{url,events}});
      const value=display(record(r.data).signing_secret,"");
      if(r.response.ok&&value){
        setSecret({label:`Signing secret for ${parsed.host}`,value});setHookUrl("");setEvents(["signal.generated","signal.closed"]);
        respond("Webhook registered. Copy the signing secret now: it is shown once.");setVersion(v=>v+1);
      }else respond(failure(r.response.status,"The service did not confirm webhook registration."),true);
    }catch{respond("Webhook registration could not be confirmed. Retry later.",true);}
    finally{setBusy(false);}
  }

  async function revokeHook(id:string){
    if(busy||confirm!=="hook:"+id)return;
    setBusy(true);respond("");
    try{
      const r=await client.DELETE("/api/v1/platform/webhooks/{webhook_endpoint_id}",{params:{path:{webhook_endpoint_id:id}}});
      if(r.response.ok&&record(r.data).revoked===true){setConfirm("");respond("The service confirmed this webhook is removed.");setVersion(v=>v+1);}
      else respond(failure(r.response.status,"Removal could not be confirmed. Refresh and retry."),true);
    }catch{respond("Removal could not be verified. Retry.",true);}
    finally{setBusy(false);}
  }

  function confirmRow(kind:"key"|"hook",id:string,label:string){
    const token=kind+":"+id;
    return confirm===token?
      <div className="ui-confirm" role="group" aria-label={`Confirm revoking ${label}`}>
        <p>Revoke {label}? Integrations using it stop working immediately.</p>
        <button className="ui-btn" type="button" disabled={busy} onClick={()=>setConfirm("")}>Keep</button>
        <button className="ui-btn" type="button" disabled={busy} onClick={()=>kind==="key"?revokeKey(id):revokeHook(id)}>{busy?"Revoking…":"Confirm revoke"}</button>
      </div>:
      <button className="ui-btn" type="button" onClick={()=>setConfirm(token)}>Revoke</button>;
  }

  if(loading)return <section className="ui-card" aria-busy="true"><h2>Developer access</h2><p>Loading API keys and webhooks…</p></section>;

  return <section className="ws-stack" aria-labelledby="developer-access-title">
    <section className="ui-card">
      <p className="ui-eyebrow">DEVELOPER ACCESS</p>
      <h2 id="developer-access-title">API keys and webhooks</h2>
      <p>Read-only API keys and signed outbound webhooks for your own tools. None of these credentials can place broker orders or move money.</p>
      {secret&&<div className="ui-notice ui-notice--warning" role="status">
        <p><strong>{secret.label}</strong> — shown once. Store it in a password manager or secret store.</p>
        <code className="ui-secret" aria-label={secret.label}>{secret.value}</code>
        <div className="ui-actions">
          <button className="ui-btn" type="button" onClick={()=>{void navigator.clipboard?.writeText(secret.value).then(()=>respond("Copied to the clipboard."),()=>respond("Copy failed. Select the text instead.",true));}}>Copy</button>
          <button className="ui-btn" type="button" onClick={()=>setSecret(null)}>I stored it, hide</button>
        </div>
      </div>}
      {notice&&<p className={error?"ui-feedback ui-feedback--error":"ui-feedback"} role={error?"alert":"status"}>{notice}</p>}
    </section>

    <section className="ui-card">
      <h2>API keys</h2>
      {data.keys===null?<p className="ui-notice ui-notice--neutral">{data.keyStatus===403?"Your plan does not include REST API access.":"API keys are unavailable: "+statusText(data.keyStatus)}</p>:
        data.keys.length?<div className="ws-cards">{data.keys.map((k,i)=>{
          const id=display(k.key_id,"");const name=display(k.name,"Unnamed key");
          const keyScopesList=Array.isArray(k.scopes)?k.scopes.filter((s):s is string=>typeof s==="string"):[];
          return <article className="ui-card" key={id||i}>
            <p className="ui-eyebrow">{k.active===true?"ACTIVE":"REVOKED"}</p>
            <h3>{name}</h3>
            <dl className="ui-kv">
              <div className="ui-kv-row"><dt>Prefix</dt><dd><code>{display(k.key_prefix)}</code></dd></div>
              <div className="ui-kv-row"><dt>Scopes</dt><dd>{keyScopesList.length?keyScopesList.join(", "):"Unreported"}</dd></div>
              <div className="ui-kv-row"><dt>Last used</dt><dd>{timeLabel(k.last_used_at)}</dd></div>
              <div className="ui-kv-row"><dt>Expires</dt><dd>{timeLabel(k.expires_at)}</dd></div>
            </dl>
            {k.active===true&&id&&confirmRow("key",id,`key “${name}”`)}
          </article>;})}</div>:
        <div className="ui-empty"><strong>No API keys yet.</strong><p>Create one below. The full key is shown only once.</p></div>}
      {data.keys!==null&&<form className="ui-form" onSubmit={createKey}>
        <div className="ui-form-grid">
          <label className="ui-field">Key name
            <input className="ui-input" type="text" required maxLength={120} autoComplete="off" value={keyName} onChange={e=>setKeyName(e.target.value)} placeholder="Spreadsheet sync"/>
          </label>
          <label className="ui-field">Expires after (days)
            <input className="ui-input" type="number" min={1} max={3650} step={1} required value={days} onChange={e=>setDays(e.target.value)}/>
          </label>
        </div>
        <fieldset className="ui-fieldset"><legend>Scopes</legend><div className="ui-check-row">
          {keyScopes.map(([value,label])=><label className="ui-check" key={value}><input type="checkbox" checked={scopes.includes(value)} onChange={e=>setScopes(c=>e.target.checked?[...c,value]:c.filter(s=>s!==value))}/>{label}</label>)}
        </div></fieldset>
        <button type="submit" className="ui-btn ui-btn--primary" disabled={busy}>{busy?"Working…":"Create API key"}</button>
      </form>}
    </section>

    <section className="ui-card">
      <h2>Outbound webhooks</h2>
      {data.hooks===null?<p className="ui-notice ui-notice--neutral">{data.hookStatus===403?"Your plan does not include outbound webhooks.":"Webhooks are unavailable: "+statusText(data.hookStatus)}</p>:
        data.hooks.length?<div className="ws-cards">{data.hooks.map((h,i)=>{
          const id=display(h.webhook_endpoint_id,"");const url=display(h.url,"Endpoint");
          const subscribed=Array.isArray(h.subscribed_events)?h.subscribed_events.filter((s):s is string=>typeof s==="string"):[];
          return <article className="ui-card" key={id||i}>
            <p className="ui-eyebrow">{h.active===true?"ACTIVE":"INACTIVE"}</p>
            <h3 className="ui-break">{url}</h3>
            <dl className="ui-kv">
              <div className="ui-kv-row"><dt>Events</dt><dd>{subscribed.length?subscribed.join(", "):"Unreported"}</dd></div>
              <div className="ui-kv-row"><dt>Created</dt><dd>{timeLabel(h.created_at)}</dd></div>
            </dl>
            {h.active===true&&id&&confirmRow("hook",id,"this webhook")}
          </article>;})}</div>:
        <div className="ui-empty"><strong>No webhooks registered.</strong><p>Deliveries are signed with a secret shown once at creation.</p></div>}
      {data.hooks!==null&&<form className="ui-form" onSubmit={createHook}>
        <label className="ui-field">Endpoint URL (public https only)
          <input className="ui-input" type="url" required maxLength={2048} inputMode="url" autoComplete="off" value={hookUrl} onChange={e=>setHookUrl(e.target.value)} placeholder="https://example.com/hooks/signalrank"/>
        </label>
        <fieldset className="ui-fieldset"><legend>Events</legend><div className="ui-check-row">
          {webhookEvents.map(([value,label])=><label className="ui-check" key={value}><input type="checkbox" checked={events.includes(value)} onChange={e=>setEvents(c=>e.target.checked?[...c,value]:c.filter(s=>s!==value))}/>{label}</label>)}
        </div></fieldset>
        <button type="submit" className="ui-btn ui-btn--primary" disabled={busy}>{busy?"Working…":"Register webhook"}</button>
      </form>}
    </section>
  </section>;
}
