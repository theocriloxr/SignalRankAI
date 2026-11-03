"use client";

import { useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, record, rows } from "../lib/presentation";

/** The backend returns a provider-hosted configuration URL. No browser app
 * credentials are collected, saved or sent to third parties by this form. */
function externalHttpsUrl(value:unknown):{href:string;hostname:string}|null {
  if(typeof value!=="string"||value.length>4096)return null;
  try{
    const uri=new URL(value);
    if(uri.protocol!=="https:"||uri.username||uri.password||uri.port||
      uri.hostname==="localhost"||uri.hostname.endsWith(".localhost")||
      /^(?:127\.|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(uri.hostname)||
      /^[\d.]+$/.test(uri.hostname)||uri.hostname==="[::1]") return null;
    return {href:uri.href,hostname:uri.hostname};
  }catch{return null;}
}

type Broker={broker:string;servers:string[]};
export function DemoBrokerConnection({onChanged}:{onChanged:()=>void}){
  const [platform,setPlatform]=useState<"mt4"|"mt5">("mt5");
  const [query,setQuery]=useState("");
  const [brokers,setBrokers]=useState<Broker[]|null>(null);
  const [selectedServer,setSelectedServer]=useState("");
  const [brokerName,setBrokerName]=useState("");
  const [label,setLabel]=useState("");
  const [searching,setSearching]=useState(false);
  const [creating,setCreating]=useState(false);
  const [error,setError]=useState("");
  const [link,setLink]=useState<{href:string;hostname:string}|null>(null);
  const [connectionId,setConnectionId]=useState("");
  const [providerMessage,setProviderMessage]=useState("");

  async function findServers(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(searching||query.trim().length<2)return;
    setSearching(true);setError("");setBrokers(null);setSelectedServer("");
    try{
      const r=await client.GET("/api/v1/platform/broker/metatrader/servers",{
        params:{query:{platform,q:query.trim().slice(0,128)}},
      });
      if(r.response.ok&&r.data&&r.data.success===true){
        const groups=rows(r.data.brokers).flatMap(row=>{
          const name=display(row.broker,"");
          const servers=Array.isArray(row.servers)?row.servers.filter((x):x is string=>typeof x==="string"&&x.trim().length>1):[];
          return name&&servers.length?[{broker:name,servers}]:[];
        });
        setBrokers(groups);
      }else setError(r.response.status===503?"MetaTrader server search isn't working right now. We've been told; try again later.":"That search didn't work. Check the spelling and try again.");
    }catch{setError("We couldn't reach the server search. Nothing was created.");}
    finally{setSearching(false);}
  }

  function selectServer(server:string,broker:string){
    setSelectedServer(server);setBrokerName(broker);setLink(null);setConnectionId("");setError("");
  }

  async function requestLink(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(!selectedServer||creating)return;
    setCreating(true);setError("");setLink(null);setConnectionId("");setProviderMessage("");
    try{
      const r=await client.POST("/api/v1/platform/broker/metatrader/secure-link",{
        body:{
          platform,server:selectedServer,broker_name:brokerName||null,
          account_label:label.trim()||null,environment:"demo",ttl_days:3,
        },
      });
      const data=record(r.data);
      if(r.response.ok&&data.success===true){
        const connection=record(data.connection);
        const id=display(connection.connection_id,"");
        const url=externalHttpsUrl(data.configuration_link);
        if(id){
          // Keep the provider link rendered until the user explicitly returns:
          // refreshing WorkspaceLive here would unmount this one-time link.
          setConnectionId(id);
          if(url){setLink(url);setProviderMessage("Done. Enter your demo login on the provider's page, then come back and check the account.");}
          else {setError("The link we got back looked wrong, so we're not showing it. Please contact support with the reference below.");}
        }else setError("The provider didn't confirm the account. Nothing was linked.");
      }else setError(r.response.status===503?"MetaTrader linking is busy or down. Try again later.":r.response.status===403?"Your plan doesn't allow another broker account.":"The provider didn't send a setup link. Check your broker list before trying again.");
    }catch{setError("We didn't get an answer. Check your broker list first so you don't create it twice.");}
    finally{setCreating(false);}
  }

  return <section className="ui-card" aria-labelledby="sr-demo-link-heading">
    <div><p className="ui-eyebrow">Start with a demo account</p>
      <h2 id="sr-demo-link-heading">Connect a MetaTrader demo account</h2></div>
    <p className="ui-notice ui-notice--neutral">Link a MetaTrader 4 or 5 <strong>demo</strong> account, not a live or prop one. You type your login on the provider&rsquo;s own page, not here. Linking it does not turn on auto-execution.</p>
    <form className="ui-form" role="search" onSubmit={findServers}>
      <div className="ui-form-grid"><label className="ui-field">MetaTrader version
        <select className="ui-select" value={platform} onChange={e=>{setPlatform(e.target.value as "mt4"|"mt5");setBrokers(null);setSelectedServer("");}}>
          <option value="mt5">MetaTrader 5</option><option value="mt4">MetaTrader 4</option>
        </select>
      </label><label className="ui-field">Search known demo broker servers
        <input className="ui-input" autoComplete="off" value={query} onChange={e=>setQuery(e.target.value)} minLength={2} maxLength={128} placeholder="Search broker name or server"/>
      </label></div>
      <button className="ui-btn" disabled={searching||query.trim().length<2} type="submit">{searching?"Checking servers…":"Search broker servers"}</button>
    </form>
    {brokers!==null&&<div className="ws-stack">
      {!brokers.length&&<p role="status">No matching broker servers were returned by the configured provider.</p>}
      {brokers.map((broker,i)=><div key={i} className="ws-subsection">
        <h3>{broker.broker}</h3>
        <div className="ui-actions">{broker.servers.map((server,j)=><button key={j} type="button" className={selectedServer===server?"ui-btn ui-btn--sm is-selected":"ui-btn"}
          aria-pressed={selectedServer===server} onClick={()=>selectServer(server,broker.broker)}>{server}</button>)}</div>
      </div>)}
    </div>}
    {selectedServer&&<form className="ui-form ui-card ui-card--muted" onSubmit={requestLink}>
      <p><strong>Selected:</strong> {brokerName}, server {selectedServer} ({platform.toUpperCase()})</p>
      <label className="ui-field">Account label (optional)
        <input className="ui-input" autoComplete="off" value={label} onChange={e=>setLabel(e.target.value)} maxLength={128} placeholder="Practice account"/>
      </label>
      <p>No passwords, API keys or account login IDs are entered here. The provider will collect the needed credentials through its own secure link.</p>
      <button className="ui-btn ui-btn--primary" type="submit" disabled={creating||Boolean(connectionId)}>{creating?"Getting the link…":"Get setup link"}</button>
    </form>}
    {providerMessage&&<p role="status" className="ui-feedback">{providerMessage}</p>}
    {link&&<div className="ui-confirm">
      <strong>Your setup link</strong>
      <p>Check the address belongs to the provider before you type your demo login: <code>{link.hostname}</code>.</p>
      <a className="ui-btn" href={link.href} target="_blank" rel="noopener noreferrer">Open the provider&rsquo;s page ↗</a>
      <p>When you&rsquo;re done there, come back and press the button below.</p>
      <button type="button" className="ui-btn" onClick={onChanged}>I finished provider setup — refresh broker accounts</button>
    </div>}
    {connectionId&&<p className="ui-eyebrow">Connection reference: {connectionId}</p>}
    {error&&<p role="alert" className="ui-feedback ui-feedback--error">{error}</p>}
  </section>;
}
