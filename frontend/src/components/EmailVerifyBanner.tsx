"use client";

import { useEffect, useState } from "react";
import client from "../lib/client";
import { record } from "../lib/presentation";

/**
 * Every page asks an unverified user to verify their email until they do
 * (owner request, 9 Nov 2026: "ensure users verify their emails"). Email
 * updates for signals and trades only go to verified addresses.
 */
export function EmailVerifyBanner() {
  const [email, setEmail] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let off = false;
    const load = async () => {
      try {
        const r = await client.GET("/api/v1/platform/me");
        const user = record(record(r.data).user);
        if (!off && r.response.ok && typeof user.primary_email === "string" && user.primary_email && !user.email_verified_at) {
          setEmail(user.primary_email);
        }
      } catch { /* the page itself reports connection problems */ }
    };
    void load();
    return () => { off = true; };
  }, []);
  if (!email) return null;
  const send = async () => {
    setBusy(true); setMessage("");
    try {
      const r = await client.POST("/api/v1/platform/auth/email-verification/request");
      setMessage(r.response.ok ? `Sent to ${email}. The link works for 30 minutes.` : "That didn't send. Try again in a minute.");
    } catch { setMessage("That didn't send. Try again in a minute."); }
    finally { setBusy(false); }
  };
  return <section className="ws-verify" role="region" aria-label="Verify your email">
    <p><b>Verify your email.</b> Confirm <b>{email}</b> to get signal and trade updates by email and to keep your account recoverable.</p>
    <div className="ui-actions">
      <button type="button" className="ui-btn ui-btn--primary ui-btn--sm" disabled={busy} onClick={send}>{busy ? "Sending…" : "Send verification link"}</button>
      {message && <span role="status" className="ws-verify-status">{message}</span>}
    </div>
  </section>;
}
