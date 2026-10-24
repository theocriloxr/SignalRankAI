"use client";

import { useEffect, useState } from "react";
import client from "../lib/client";
import { record, telegramLinkState, timeLabel, utcTimestamp, type Row } from "../lib/presentation";

type LinkProof = { code: string; expires: number; href: string | null };

export function TelegramConnection({ user, onRefresh }: { user: Row; onRefresh: () => void }) {
  const state = telegramLinkState(user);
  const [proof, setProof] = useState<LinkProof | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!proof) return;
    const timer = window.setTimeout(() => {
      setProof(null);
      setMessage("This linking code has expired. Request a new code to continue.");
    }, Math.max(0, proof.expires - Date.now()));
    return () => window.clearTimeout(timer);
  }, [proof]);

  async function requestLink() {
    if (busy || !["unlinked", "pending"].includes(state)) return;
    setBusy(true); setMessage(""); setProof(null);
    try {
      const response = await client.POST("/api/v1/platform/account/telegram-link", { body: { return_path: "/app/settings" } });
      if (response.response.status === 409) {
        setMessage("Your connection status has changed. Refreshing your account.");
        onRefresh(); return;
      }
      const payload = record(response.data);
      const code = typeof payload.code === "string" ? payload.code : "";
      const expires = typeof payload.expires_at === "string" ? utcTimestamp(payload.expires_at) : NaN;
      if (!response.response.ok || !/^[A-F0-9]{10}$/.test(code) || !Number.isFinite(expires) || expires <= Date.now()) {
        setMessage("A valid linking code could not be confirmed. Refresh your account and retry."); return;
      }
      let href: string | null = null;
      if (typeof payload.telegram_deep_link === "string") {
        try {
          const link = new URL(payload.telegram_deep_link);
          if (link.origin === "https://t.me" && !link.username && !link.password &&
              /^\/[A-Za-z0-9_]{5,64}$/.test(link.pathname) && link.searchParams.get("start") === `link_${code}`) {
            href = link.href;
          }
        } catch { /* Manual code remains available when a bot URL is unavailable. */ }
      }
      setProof({code, expires, href});
    } catch { setMessage("Telegram linking is temporarily unavailable. Please retry."); }
    finally { setBusy(false); }
  }

  return <section className="ui-card" aria-labelledby="sr-telegram-title">
    <h2 id="sr-telegram-title">Telegram connection</h2>
    {state === "linked" ? <p role="status">Telegram is connected to this account. You do not need to link it again.</p>
      : state === "review" ? <p role="status">Telegram ownership is verified. Your account history is awaiting reconciliation; reconnecting is unnecessary.</p>
      : state === "unknown" ? <p>Connection status is unavailable. Refresh your account before making changes.</p>
      : <><p>{state === "pending" ? "A linking request is waiting for completion in Telegram." : "Connect Telegram to keep your account and eligible signal deliveries together."}</p>
        {!proof && <button className="ui-btn" type="button" disabled={busy} onClick={requestLink}>
          {busy ? "Preparing code…" : state === "pending" ? "Replace linking code" : "Link Telegram"}</button>}
      </>}
    {proof && ["unlinked", "pending"].includes(state) && <div className="ui-form">
      <p>In the SignalRankAI bot, send <code>/link {proof.code}</code>. Keep this one-time code private.</p>
      <p>Expires {timeLabel(new Date(proof.expires).toISOString())}</p>
      {proof.href && <a className="ui-btn" href={proof.href} target="_blank" rel="noopener noreferrer">Open SignalRankAI in Telegram</a>}
      <p>After completing the link, refresh the connection below.</p>
    </div>}
    <button className="ui-btn" type="button" disabled={busy} onClick={onRefresh}>Refresh Telegram connection</button>
    {message && <p role="status">{message}</p>}
  </section>;
}
