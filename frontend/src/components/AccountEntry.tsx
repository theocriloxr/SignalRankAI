"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import client from "../lib/client";
import { record } from "../lib/presentation";

export function AccountEntry() {
  const [mode, setMode] = useState<"login"|"register">("login");
  const [stage, setStage] = useState<"credentials"|"mfa">("credentials");
  const [token, setToken] = useState("");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function verifyAuthenticatedSession() {
    const me = await client.GET("/api/v1/platform/me");
    if (me.response.ok && record(me.data).user) {
      router.replace("/app"); router.refresh();
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
      } else if (mode === "register") {
        const password = String(data.get("password")||"");
        if (password !== String(data.get("confirm_password")||"")) {
          setMessage("Passwords do not match.");return;
        }
        response = await client.POST("/api/v1/platform/auth/register", {
          body: { email: String(data.get("email")||"").trim(), password, display_name: String(data.get("name")||"").trim(), client_type:"web", signup_source:"web", landing_path:"/app" },
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

  function reset(next: "login"|"register") {
    setMode(next);setStage("credentials");setToken("");setMessage("");
  }

  return <main className="sr-auth"><div className="sr-auth-layout">
    <section className="sr-auth-copy">
      <Link href="/" className="sr-auth-wordmark">SignalRank<span>AI</span></Link>
      <p className="sr-overline">Identity protected / Broker controls separate</p>
      <h1>Research first. <em>Execute only when certified.</em></h1>
      <p>Access your personal signal history, risk evidence, paper trading and verified broker records. Logging in does not activate live trading.</p>
      <div className="sr-auth-cert"><span>01 / Cookie session</span><span>02 / MFA where enabled</span><span>03 / Account-scoped records</span></div>
    </section>
    <section className="sr-auth-card" aria-labelledby="sr-auth-title">
      <p className="sr-overline">{stage==="mfa"?"Additional verification":"Account access"}</p>
      <h2 id="sr-auth-title">{stage==="mfa"?"Verify your identity":mode==="register"?"Create your SignalRank account":"Welcome back"}</h2>
      <p>Credentials are sent to the canonical account service. No session token is stored in browser local storage.</p>
      <form onSubmit={submit}>
        {stage==="mfa"?<label>Authenticator code<input name="code" inputMode="numeric" autoComplete="one-time-code" minLength={6} maxLength={8} required /></label>:
        <>
          {mode==="register"&&<label>Display name<input name="name" autoComplete="name" maxLength={100}/></label>}
          <label>Email address<input name="email" type="email" autoComplete="email" required maxLength={255}/></label>
          <label>Password<input name="password" type="password" autoComplete={mode==="register"?"new-password":"current-password"} minLength={mode==="register"?10:undefined} required/></label>
          {mode==="register"&&<label>Confirm password<input name="confirm_password" type="password" autoComplete="new-password" required/></label>}
        </>}
        {message&&<p className="sr-form-message" role="status">{message}</p>}
        <button className="button" type="submit" disabled={busy}>{busy?"Verifying…":stage==="mfa"?"Verify code":mode==="register"?"Create account":"Sign in"}</button>
      </form>
      {stage==="mfa"?<button className="sr-auth-switch" type="button" onClick={()=>reset("login")}>Use another account</button>:
      <button className="sr-auth-switch" type="button" onClick={()=>reset(mode==="login"?"register":"login")}>{mode==="login"?"New to SignalRank? Create an account":"Already have an account? Sign in"}</button>}
      {stage==="credentials"&&<Link href="/recover" className="sr-auth-switch">Forgot your password?</Link>}
      {stage==="credentials"&&<Link href="/magic-login" className="sr-auth-switch">Sign in with an email link</Link>}
      <p className="sr-auth-disclaimer">Trading carries risk. Market data, execution eligibility and financial records must be verified independently.</p>
    </section>
  </div></main>;
}
