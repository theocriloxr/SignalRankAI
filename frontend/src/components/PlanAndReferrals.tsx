"use client";

import { useEffect, useState } from "react";
import client from "../lib/client";
import { display, finite, record, statusText, type Row } from "../lib/presentation";
import { Badge } from "./ui/primitives";

type Loaded = {plan:Row|null;referral:Row|null;planStatus:number;referralStatus:number};

const limitLabels:[string,string,(v:number)=>string][] = [
  ["daily_signals","Signals per day",v=>String(v)],
  ["history_days","History window",v=>`${v} days`],
  ["max_tp_levels","Take-profit levels",v=>String(v)],
  ["delivery_delay_minutes","Delivery delay",v=>v===0?"Real time":`${v} min`],
  ["minimum_signal_score","Minimum signal score",v=>String(v)],
];

const strings=(value:unknown)=>Array.isArray(value)?value.filter((v):v is string=>typeof v==="string"&&v.length>0):[];
const words=(value:string)=>value.replaceAll("_"," ");

/** Read-only view of what the current plan includes and referral progress. */
export function PlanAndReferrals(){
  const [data,setData]=useState<Loaded|null>(null);
  const [copied,setCopied]=useState("");

  useEffect(()=>{
    let cancelled=false;
    async function load(){
      const [plan,referral]=await Promise.allSettled([client.GET("/api/v1/platform/entitlements"),client.GET("/api/v1/platform/referrals")]);
      if(cancelled)return;
      const p=plan.status==="fulfilled"?plan.value:null, r=referral.status==="fulfilled"?referral.value:null;
      setData({
        plan:p?.response.ok?record(p.data):null, referral:r?.response.ok?record(r.data):null,
        planStatus:p?.response.status??0, referralStatus:r?.response.status??0,
      });
    }
    void load();
    return ()=>{cancelled=true;};
  },[]);

  if(!data)return <section className="ui-card" aria-busy="true"><h2>Plan and referrals</h2><p>Loading plan details…</p></section>;
  const plan=data.plan, referral=data.referral;
  const limits=record(plan?.limits);
  const earned=finite(referral?.premium_days_earned), toward=finite(referral?.toward_next), needed=finite(referral?.needed_for_next);
  const progress=toward!==null&&needed!==null&&needed>0?Math.max(0,Math.min(100,Math.round(toward/needed*100))):null;

  function copy(label:string,value:string){
    void navigator.clipboard?.writeText(value).then(()=>setCopied(label),()=>setCopied(""));
  }

  return <section className="ws-stack" aria-labelledby="plan-title">
    <section className="ui-card">
      <p className="ui-eyebrow">YOUR PLAN</p>
      <h2 id="plan-title">{plan?`${display(plan.tier,"Current").toUpperCase()} plan`:"Plan details"}</h2>
      {!plan?<p className="ui-notice ui-notice--neutral">Plan details are unavailable: {statusText(data.planStatus)}</p>:<>
        <dl className="ui-kv">
          {limitLabels.map(([key,label,format])=>{const v=finite(limits[key]);return <div className="ui-kv-row" key={key}><dt>{label}</dt><dd>{v===null?"Unreported":format(v)}</dd></div>;})}
          <div className="ui-kv-row"><dt>Asset classes</dt><dd>{strings(plan.allowed_asset_classes).map(words).join(", ")||"Unreported"}</dd></div>
          <div className="ui-kv-row"><dt>Risk profiles</dt><dd>{strings(plan.allowed_profiles).map(words).join(", ")||"Unreported"}</dd></div>
        </dl>
        {strings(plan.features).length>0&&<><h3>Included features</h3><ul className="ui-tags">{strings(plan.features).map(f=><li key={f}><Badge>{words(f)}</Badge></li>)}</ul></>}
        <p className="ui-muted">Policy version {display(plan.policy_version,"unreported")}. Limits are enforced by the server; this page only displays them.</p>
      </>}
    </section>

    <section className="ui-card">
      <p className="ui-eyebrow">REFERRALS</p>
      <h2>Invite traders</h2>
      {!referral?<p className="ui-notice ui-notice--neutral">Referral details are unavailable: {statusText(data.referralStatus)}</p>:<>
        <dl className="ui-kv">
          <div className="ui-kv-row"><dt>Your code</dt><dd><code>{display(referral.code)}</code></dd></div>
          <div className="ui-kv-row"><dt>Referred accounts</dt><dd>{display(referral.total_referrals,"0")}</dd></div>
          <div className="ui-kv-row"><dt>Premium days earned</dt><dd>{earned===null?"Unreported":earned}</dd></div>
        </dl>
        {progress!==null&&<div>
          <p>{toward} of {needed} qualifying referrals toward the next {display(referral.reward_days,"reward")} premium days.</p>
          <div className="ui-meter" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-label="Progress to next referral reward"><span style={{width:`${progress}%`}}/></div>
        </div>}
        <div className="ui-actions">
          {typeof referral.web_url==="string"&&referral.web_url.startsWith("https://")&&<button className="ui-btn" type="button" onClick={()=>copy("Web invite link",String(referral.web_url))}>Copy web invite link</button>}
          {typeof referral.telegram_url==="string"&&referral.telegram_url.startsWith("https://t.me/")&&<button className="ui-btn" type="button" onClick={()=>copy("Telegram invite link",String(referral.telegram_url))}>Copy Telegram link</button>}
        </div>
        {copied&&<p className="ui-feedback" role="status">{copied} copied.</p>}
        <p className="ui-muted">Rewards are premium access days, never cash. Referral credit is granted by the server after the invited account qualifies.</p>
      </>}
    </section>
  </section>;
}
