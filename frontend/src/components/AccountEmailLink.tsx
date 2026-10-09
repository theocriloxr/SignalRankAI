"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import client from "../lib/client";
import { record } from "../lib/presentation";

/** Existing backend emails /app?verify_email= or /app?magic_login= one-time links.
 * Do not consume tokens on first page load: link scanners may prefetch email URLs. */
export function AccountEmailLink({ kind, token }: {
  kind: "verify"|"magic"; token: string;
}) {
  const [busy,setBusy]=useState(false);
  const [stage,setStage]=useState<"confirm"|"mfa"|"done">("confirm");
  const [mfaToken,setMfaToken]=useState("");
  const [message,setMessage]=useState("");
  const isVerification=kind==="verify";

  async function finishSession() {
    const me=await client.GET("/api/v1/platform/me");
    if (me.response.ok && record(me.data).user) {
      window.location.replace("/app");return;
    }
    setMessage("The sign-in session could not be verified. Sign in manually to continue.");
  }

  async function consume() {
    if(busy)return;
    setBusy(true);setMessage("");
    try {
      if (isVerification) {
        const result=await client.POST("/api/v1/platform/auth/email-verification/complete",{
          body:{token,client_type:"web"},
        });
        if(result.response.ok && record(result.data).verified===true) {
          setStage("done");
          setMessage("Email address verified. Sign in to your account.");
        } else setMessage("The verification link is expired or invalid. Request a new link from the authenticated account.");
      } else {
        const result=await client.POST("/api/v1/platform/auth/magic-link/complete",{
          body:{token,client_type:"web"},
        });
        if (!result.response.ok || !result.data) {
          setMessage("The sign-in link could not be verified. It may already have been used.");
        } else {
          const payload=record(result.data);
          if(payload.mfa_required===true && typeof payload.mfa_token==="string") {
            setMfaToken(payload.mfa_token);setStage("mfa");
            setMessage("Additional authentication is required before a session can be opened.");
          } else await finishSession();
        }
      }
    } catch { setMessage("The account service is currently unreachable. No access has been confirmed."); }
    finally {setBusy(false);}
  }

  async function verifyMfa(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(busy||!mfaToken)return;
    setBusy(true);setMessage("");
    const code=String(new FormData(event.currentTarget).get("code")||"").trim();
    try {
      const r=await client.POST("/api/v1/platform/auth/mfa/complete",{
        body:{token:mfaToken,code,client_type:"web"},
      });
      if(r.response.ok) await finishSession();
      else setMessage("Authenticator proof could not be verified. Check the code or sign in manually.");
    }catch{setMessage("Authenticator service unavailable. No session has been confirmed.");}
    finally{setBusy(false);}
  }

  return <main className="sr-auth"><section className="sr-auth-card sr-recovery-card">
    <Link href="/" className="sr-auth-wordmark">SignalRank<span>AI</span></Link>
    <p className="sr-overline">Secure one-time link / {isVerification?"Email verification":"Magic sign-in"}</p>
    <h1>{isVerification?"Verify your email":"Confirm your sign-in"}</h1>
    <p>{isVerification
      ?"Confirm that you intended to verify your email address. This never enables broker trading."
      :"Continue only if you requested this sign-in. MFA and account policies remain mandatory."}</p>
    {stage==="confirm"&&<button className="button" type="button" onClick={consume} disabled={busy}>
      {busy?"Checking…":isVerification?"Verify email":"Continue securely"}
    </button>}
    {stage==="mfa"&&<form onSubmit={verifyMfa}><label>Authenticator code
      <input name="code" required minLength={6} maxLength={32} autoComplete="one-time-code" inputMode="numeric"/>
    </label><button className="button" disabled={busy} type="submit">{busy?"Verifying…":"Verify and sign in"}</button></form>}
    {message&&<p className="sr-form-message" role="status">{message}</p>}
    {stage==="done"&&<Link className="sr-secondary-action" href="/login">Go to sign in</Link>}
    <Link className="sr-secondary-action" href="/login">Use normal sign in instead</Link>
  </section></main>;
}
