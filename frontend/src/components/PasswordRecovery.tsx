"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
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

  return <main className="sr-auth"><section className="sr-auth-card sr-recovery-card">
    <Link href="/" className="sr-auth-wordmark">SignalRank<span>AI</span></Link>
    <p className="sr-overline">Account recovery / No trading permissions changed</p>
    <h1>{stage==="request"?"Recover account access":"Choose a new password"}</h1>
    <p>Recovery changes sign-in credentials only. Broker connections, risk controls and trading permissions remain governed by their existing verification policies.</p>
    {!finished&&<form onSubmit={submit}>
      {stage==="request"?<label>Email address<input type="email" name="email" required autoComplete="email" maxLength={255}/></label>:
      <><label>New password<input name="password" type="password" required minLength={10} maxLength={256} autoComplete="new-password"/></label><label>Confirm password<input name="confirmation" type="password" required autoComplete="new-password"/></label></>}
      <button className="button" type="submit" disabled={busy}>{busy?"Processing…":stage==="request"?"Send recovery instructions":"Update password"}</button>
    </form>}
    {message&&<p className="sr-form-message" role="status">{message}</p>}
    {finished?<Link className="sr-secondary-action" href="/login">Return to sign in</Link>:
      stage==="complete"?<button type="button" className="sr-auth-switch" onClick={()=>{setStage("request");setMessage("")}}>Request another recovery link</button>:<Link href="/login" className="sr-auth-switch">Back to sign in</Link>}
  </section></main>;
}
