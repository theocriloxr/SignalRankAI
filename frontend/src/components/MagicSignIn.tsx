"use client";

import Link from "next/link";
import { SiteCredit } from "./SiteCredit";
import { BrandLink } from "./AuthFrame";
import { Icon } from "./ui/Icon";
import { useState, type FormEvent } from "react";
import client from "../lib/client";

/** Non-enumerating login link request. One-time tokens are never stored in browser storage. */
export function MagicSignIn() {
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [done,setDone]=useState(false);
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(busy)return;
    setBusy(true);setMessage("");
    const email=String(new FormData(event.currentTarget).get("email")||"").trim();
    try{
      const result=await client.POST("/api/v1/platform/auth/magic-link/request",{body:{email}});
      if(result.response.status===429)setMessage("Please wait before requesting another link.");
      else if(result.response.ok) {
        setDone(true);
        setMessage("If this address has an active account, sign-in instructions will be sent. The link may require MFA.");
      } else setMessage("Email sign-in is temporarily unavailable. Try password sign-in instead.");
    }catch{setMessage("Account service unavailable. No link request was confirmed.");}
    finally{setBusy(false);}
  }
  return <main className="auth-solo">
    <BrandLink/>
    <section className="auth-card" aria-labelledby="magic-title">
      <div><p className="ui-eyebrow">Secure email link</p><h2 id="magic-title">Sign in by email</h2></div>
      <p>Request a one-time sign-in link. No broker permission is changed, and existing MFA remains required.</p>
      {!done&&<form className="ui-form" onSubmit={submit}><label className="ui-field">Account email address
        <input className="ui-input" type="email" name="email" autoComplete="email" required maxLength={320}/>
      </label><button type="submit" className="ui-btn ui-btn--primary ui-btn--lg ui-btn--block" disabled={busy}><Icon name="mail"/>{busy?"Requesting…":"Send sign-in link"}</button></form>}
      {message&&<p className={done?"ui-feedback":"ui-feedback ui-feedback--error"} role="status">{message}</p>}
      <div className="auth-links"><Link href="/login"><Icon name="arrowLeft" size={14}/> Use password sign-in</Link></div>
    </section>
    <div className="auth-foot"><SiteCredit compact /></div>
  </main>;
}
