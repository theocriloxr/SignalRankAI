"use client";

import { useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, record, rows, type Row } from "../lib/presentation";

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
      }else setError(r.response.status===503?"MetaTrader server discovery is not configured or unavailable. An administrator must restore the provider integration.":"The server search was not verified. Check the spelling or retry.");
    }catch{setError("Server discovery could not be reached. No connection has been created.");}
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
          setConnectionId(id);
          onChanged();
          if(url){setLink(url);setProviderMessage("A demo account configuration request was created. Complete credentials on the provider site, then return here and verify the connection.");}
          else {setError("A connection was created but its provider link was missing or unsafe. Do not enter credentials at an unverified address. Contact support with the connection reference.");}
        }else setError("The provider response had no canonical connection identity. No completed connection is confirmed.");
      }else setError(r.response.status===503?"MetaTrader integration is unavailable or out of capacity. No working secure link was confirmed.":r.response.status===403?"This account cannot add another broker connection on its current plan.":"The provider did not confirm a secure configuration link. Retry only after checking existing connections.");
    }catch{setError("The response could not be verified. Check your broker list before resubmitting to avoid duplicate requests.");}
    finally{setCreating(false);}
  }

  return <section className="sr-data-panel sr-demo-link" aria-labelledby="sr-demo-link-heading">
    <div><p className="sr-overline">Onboarding / Demo-first / Provider-hosted credentials</p>
      <h2 id="sr-demo-link-heading">Connect a MetaTrader demo account</h2></div>
    <p className="sr-risk-note">This flow only requests a provider-hosted credential entry link for an MT4 or MT5 <strong>demo</strong> account. Do not use a live or prop account here. Creating a connection does not turn on auto-execution or certify trading safety.</p>
    <form className="sr-create-form" role="search" onSubmit={findServers}>
      <div className="sr-form-grid"><label>MetaTrader version
        <select value={platform} onChange={e=>{setPlatform(e.target.value as "mt4"|"mt5");setBrokers(null);setSelectedServer("");}}>
          <option value="mt5">MetaTrader 5</option><option value="mt4">MetaTrader 4</option>
        </select>
      </label><label>Search known demo broker servers
        <input autoComplete="off" value={query} onChange={e=>setQuery(e.target.value)} minLength={2} maxLength={128} placeholder="Search broker name or server"/>
      </label></div>
      <button className="sr-secondary-action" disabled={searching||query.trim().length<2} type="submit">{searching?"Checking servers…":"Search broker servers"}</button>
    </form>
    {brokers!==null&&<div className="sr-demo-servers">
      {!brokers.length&&<p role="status">No matching broker servers were returned by the configured provider.</p>}
      {brokers.map((broker,i)=><div key={i} className="sr-demo-broker">
        <h3>{broker.broker}</h3>
        <div className="sr-demo-server-choices">{broker.servers.map((server,j)=><button key={j} type="button" className={selectedServer===server?"sr-secondary-action active":"sr-secondary-action"}
          aria-pressed={selectedServer===server} onClick={()=>selectServer(server,broker.broker)}>{server}</button>)}</div>
      </div>)}
    </div>}
    {selectedServer&&<form className="sr-create-form sr-demo-confirm" onSubmit={requestLink}>
      <p><strong>Selected:</strong> {brokerName} / {selectedServer} ({platform.toUpperCase()})</p>
      <label>Account label (optional)
        <input autoComplete="off" value={label} onChange={e=>setLabel(e.target.value)} maxLength={128} placeholder="Practice account"/>
      </label>
      <p>No passwords, API keys or account login IDs are entered here. The provider will collect the needed credentials through its own secure link.</p>
      <button className="button" type="submit" disabled={creating||Boolean(connectionId)}>{creating?"Requesting provider link…":"Request demo secure link"}</button>
    </form>}
    {providerMessage&&<p role="status" className="sr-submit-feedback">{providerMessage}</p>}
    {link&&<div className="sr-demo-link-result">
      <strong>Provider link available</strong>
      <p>Check that the destination host belongs to the expected provider before entering your demo credentials: <code>{link.hostname}</code>.</p>
      <a className="sr-secondary-action" href={link.href} target="_blank" rel="noopener noreferrer">Open provider secure setup ↗</a>
      <p>Return to SignalRankAI after provider setup. Use **read-only verification** on the matching broker account before proceeding with any certification.</p>
    </div>}
    {connectionId&&<p className="sr-overline">Connection reference: {connectionId}</p>}
    {error&&<p role="alert" className="sr-submit-feedback sr-submit-feedback--error">{error}</p>}
  </section>;
}
