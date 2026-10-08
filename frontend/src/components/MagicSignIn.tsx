"use client";

import Link from "next/link";
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
  return <main className="sr-auth"><section className="sr-auth-card sr-recovery-card">
    <Link href="/" className="sr-auth-wordmark">SignalRank<span>AI</span></Link>
    <p className="sr-overline">Account identity / Secure email link</p>
    <h1>Sign in by email.</h1>
    <p>Request a one-time sign-in link. No broker permission is changed, and existing MFA remains required.</p>
    {!done&&<form onSubmit={submit}><label>Account email address
      <input type="email" name="email" autoComplete="email" required maxLength={320}/>
    </label><button type="submit" className="button" disabled={busy}>{busy?"Requesting…":"Send sign-in link"}</button></form>}
    {message&&<p className="sr-form-message" role="status">{message}</p>}
    <Link className="sr-secondary-action" href="/login">Use password sign-in</Link>
  </section></main>;
}
