"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { SiteCredit } from "./SiteCredit";
import { AuthAside, BrandLink } from "./AuthFrame";
import { Icon } from "./ui/Icon";
import client from "../lib/client";
import { record } from "../lib/presentation";
import { safeReturnPath } from "../lib/return-path";

export function AccountEntry() {
  // Links from the Telegram bot (/app, /login_code) carry a one-time token.
  const searchParams = useSearchParams();
  const linkedCode = searchParams.get("token") || searchParams.get("activation") || "";
  const [mode, setMode] = useState<"login"|"register"|"telegram">(linkedCode ? "telegram" : "login");
  const [activationCode, setActivationCode] = useState(linkedCode);
  const [stage, setStage] = useState<"credentials"|"mfa">("credentials");
  const [token, setToken] = useState("");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function verifyAuthenticatedSession() {
    const me = await client.GET("/api/v1/platform/me");
    if (me.response.ok && record(me.data).user) {
      router.replace(safeReturnPath(new URLSearchParams(window.location.search).get("returnTo"))); router.refresh();
      return true;
    }
    setMessage("The session could not be verified. Check your connection and sign in again.");
    return false;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setMessage("");
    const data = new FormData(event.currentTarget);
    try {
      let response;
      if (stage === "mfa") {
        response = await client.POST("/api/v1/platform/auth/mfa/complete", {
          body: { token, code: String(data.get("code")||"").trim(), client_type:"web" },
        });
      } else if (mode === "telegram") {
        response = await client.POST("/api/v1/platform/auth/telegram/complete", {
          body: { token_or_code: String(data.get("token_or_code")||"").trim(), email: String(data.get("email")||"").trim(),
            password: String(data.get("password")||""), client_type: "web",
            platform_terms_accepted:data.get("platform_terms_accepted")==="on",
            privacy_acknowledged:data.get("privacy_acknowledged")==="on",
            age_eligibility_confirmed:data.get("age_eligibility_confirmed")==="on",
            marketing_consent:data.get("marketing_consent")==="on" },
        });
      } else if (mode === "register") {
        const password = String(data.get("password")||"");
        if (password !== String(data.get("confirm_password")||"")) {
          setMessage("Passwords do not match.");return;
        }
        response = await client.POST("/api/v1/platform/auth/register", {
          body: { email: String(data.get("email")||"").trim(), password, display_name: String(data.get("name")||"").trim(), client_type:"web", signup_source:"web", landing_path:"/app",
            platform_terms_accepted:data.get("platform_terms_accepted")==="on",
            privacy_acknowledged:data.get("privacy_acknowledged")==="on",
            age_eligibility_confirmed:data.get("age_eligibility_confirmed")==="on",
            marketing_consent:data.get("marketing_consent")==="on" },
        });
      } else {
        response = await client.POST("/api/v1/platform/auth/login", {
          body: { email:String(data.get("email")||"").trim(), password:String(data.get("password")||""), client_type:"web" },
        });
      }
      if (!response.response.ok || !response.data) {
        setMessage(response.response.status===429
          ? "Too many attempts. Wait before retrying."
          : response.response.status===503 ? "Secure account services are unavailable right now."
          : "The request could not be completed. Check your details and try again.");
        return;
      }
      const payload=record(response.data);
      if (payload.mfa_required === true && typeof payload.mfa_token === "string") {
        setToken(payload.mfa_token);setStage("mfa");setMessage("Enter the code from your authenticator app.");
        return;
      }
      await verifyAuthenticatedSession();
    } catch {
      setMessage("Unable to reach the secure account service. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  function reset(next: "login"|"register"|"telegram") {
    setMode(next);setStage("credentials");setToken("");setMessage("");
  }

  const title = stage==="mfa" ? "Verify your identity" : mode==="register" ? "Create your account"
    : mode==="telegram" ? "Bring your Telegram account" : "Welcome back";
  const needsConsent = mode==="register" || mode==="telegram";
  return <main className="auth">
    <AuthAside/>
    <div className="auth-main">
      <section className="auth-card" aria-labelledby="auth-title">
        <span className="auth-mobile-brand"><BrandLink/></span>
        {stage==="credentials"&&<div className="ui-segmented auth-tabs" role="group" aria-label="Account access mode">
          <button type="button" aria-pressed={mode==="login"} onClick={()=>reset("login")}>Sign in</button>
          <button type="button" aria-pressed={mode==="register"} onClick={()=>reset("register")}>Create account</button>
          <button type="button" aria-pressed={mode==="telegram"} onClick={()=>reset("telegram")}>From Telegram</button>
        </div>}
        <div>
          <p className="ui-eyebrow">{stage==="mfa"?"Additional verification":"Account access"}</p>
          <h2 id="auth-title">{title}</h2>
        </div>
        <p>{stage === "mfa" ? "Use your authenticator app to finish signing in."
          : mode === "register" ? "Start your research and paper trading workspace."
          : mode === "telegram" ? "In the SignalRankAI bot send /app or /login_code, then enter the one-time code (or open the link) and choose your web sign-in details."
          : "Sign in to continue where you left off."}</p>
        <form onSubmit={submit} className="ui-form">
          {stage==="mfa"?<label className="ui-field">Authenticator code<input className="ui-input mono" name="code" inputMode="numeric" autoComplete="one-time-code" minLength={6} maxLength={8} required autoFocus /></label>:
          <>
            {mode==="telegram"&&<label className="ui-field">One-time code<input className="ui-input mono" name="token_or_code" autoComplete="one-time-code" required maxLength={256}
              value={activationCode} onChange={event=>setActivationCode(event.target.value)}/></label>}
            {mode==="register"&&<label className="ui-field">Display name<input className="ui-input" name="name" autoComplete="name" maxLength={100}/></label>}
            <label className="ui-field">Email address<input className="ui-input" name="email" type="email" autoComplete="email" required maxLength={255}/></label>
            <label className="ui-field">Password<input className="ui-input" name="password" type="password" autoComplete={needsConsent?"new-password":"current-password"} minLength={needsConsent?10:undefined} required/>
              {needsConsent&&<small>At least 10 characters.</small>}</label>
            {mode==="register"&&<label className="ui-field">Confirm password<input className="ui-input" name="confirm_password" type="password" autoComplete="new-password" required/></label>}
            {needsConsent&&<fieldset className="ui-fieldset">
              <legend>Account agreements</legend>
              <label className="ui-consent"><input name="platform_terms_accepted" type="checkbox" required/><span>I agree to the <a href="/terms" target="_blank" rel="noopener noreferrer">Terms of Use</a>.</span></label>
              <label className="ui-consent"><input name="privacy_acknowledged" type="checkbox" required/><span>I have read the <a href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Notice</a>.</span></label>
              <label className="ui-consent"><input name="age_eligibility_confirmed" type="checkbox" required/><span>I confirm I am at least 18 and eligible to use the service.</span></label>
              <label className="ui-consent"><input name="marketing_consent" type="checkbox"/><span>Send me optional product news and marketing emails.</span></label>
            </fieldset>}
          </>}
          {message&&<p className={stage==="mfa"&&message.startsWith("Enter the code")?"ui-feedback":"ui-feedback ui-feedback--error"} role="status">{message}</p>}
          <button className="ui-btn ui-btn--primary ui-btn--lg ui-btn--block" type="submit" disabled={busy}>{busy?"Verifying…":stage==="mfa"?"Verify code":mode==="register"?"Create account":mode==="telegram"?"Activate web access":"Sign in"}</button>
        </form>
        <div className="auth-links">
          {stage==="mfa"&&<button type="button" onClick={()=>reset("login")}><Icon name="arrowLeft" size={14}/> Use another account</button>}
          {stage==="credentials"&&<Link href="/recover">Forgot your password?</Link>}
          {stage==="credentials"&&<Link href="/magic-login">Sign in with an email link instead</Link>}
        </div>
        <p className="auth-disclaimer">Trading carries risk. Market data, execution eligibility and financial records must be verified independently.</p>
      </section>
      <div className="auth-foot"><SiteCredit compact /></div>
    </div>
  </main>;
}
