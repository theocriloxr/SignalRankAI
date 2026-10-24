"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { SiteCredit } from "./SiteCredit";
import { BrandLink } from "./AuthFrame";
import { Icon } from "./ui/Icon";
import client from "../lib/client";

/** Canonical password-recovery flow. No email-existence disclosure or browser token persistence. */
export function PasswordRecovery({ initialToken = "" }: { initialToken?: string }) {
  const [stage,setStage] = useState<"request"|"complete">(initialToken ? "complete" : "request");
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState("");
  const [finished,setFinished] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);setMessage("");
    const values=new FormData(event.currentTarget);
    try {
      if (stage==="request") {
        const response=await client.POST("/api/v1/platform/auth/password-reset/request",{
          body:{email:String(values.get("email")||"").trim()},
        });
        if(response.response.status===429) setMessage("Please wait before requesting another recovery link.");
        else if(response.response.ok) {setFinished(true);setMessage("If the address has an account, the recovery instructions will be sent.");}
        else setMessage("Recovery services are unavailable. Please retry later.");
      } else {
        const password=String(values.get("password")||"");
        if (password!==String(values.get("confirmation")||"")){setMessage("Passwords do not match.");return}
        const response=await client.POST("/api/v1/platform/auth/password-reset/complete",{
          body:{token:initialToken,new_password:password},
        });
        if(response.response.ok){setFinished(true);setMessage("Password updated. Sign in with your new password.");}
        else setMessage("The reset link may be expired or invalid. Request a new recovery link.");
      }
    }catch{setMessage("The secure service could not be reached. Retry later.");}
    finally{setBusy(false)}
  }

  return <main className="auth-solo">
    <BrandLink/>
    <section className="auth-card" aria-labelledby="recovery-title">
      <div><p className="ui-eyebrow">Account recovery</p>
        <h2 id="recovery-title">{stage==="request"?"Recover account access":"Choose a new password"}</h2></div>
      <p>Recovery changes sign-in credentials only. Broker connections, risk controls and trading permissions keep their existing verification policies.</p>
      {!finished&&<form className="ui-form" onSubmit={submit}>
        {stage==="request"?<label className="ui-field">Email address<input className="ui-input" type="email" name="email" required autoComplete="email" maxLength={255}/></label>:
        <><label className="ui-field">New password<input className="ui-input" name="password" type="password" required minLength={10} maxLength={256} autoComplete="new-password"/><small>At least 10 characters.</small></label>
          <label className="ui-field">Confirm password<input className="ui-input" name="confirmation" type="password" required autoComplete="new-password"/></label></>}
        <button className="ui-btn ui-btn--primary ui-btn--lg ui-btn--block" type="submit" disabled={busy}>{busy?"Processing…":stage==="request"?"Send recovery instructions":"Update password"}</button>
      </form>}
      {message&&<p className={finished?"ui-feedback":"ui-feedback ui-feedback--error"} role="status">{message}</p>}
      <div className="auth-links">
        {finished?<Link href="/login">Return to sign in</Link>:
          stage==="complete"?<button type="button" onClick={()=>{setStage("request");setMessage("")}}>Request another recovery link</button>:<Link href="/login"><Icon name="arrowLeft" size={14}/> Back to sign in</Link>}
      </div>
    </section>
    <div className="auth-foot"><SiteCredit compact /></div>
  </main>;
}
