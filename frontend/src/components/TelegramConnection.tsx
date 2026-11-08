"use client";

import { useEffect, useRef, useState } from "react";
import client from "../lib/client";
import { record, telegramLinkState, timeLabel, utcTimestamp, type Row } from "../lib/presentation";

type LinkProof = { code: string; expires: number; href: string | null };

export function TelegramConnection({ user, onRefresh }: { user: Row; onRefresh: () => void }) {
  const state = telegramLinkState(user);
  const [proof, setProof] = useState<LinkProof | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const refreshRef = useRef(onRefresh);
  useEffect(() => { refreshRef.current = onRefresh; }, [onRefresh]);
  // While a code is open, notice the link completing without a manual refresh
  // (owner request, 8 Nov 2026: smoother app-to-Telegram linking).
  useEffect(() => {
    if (!proof) return;
    const poll = window.setInterval(() => { refreshRef.current(); }, 5000);
    return () => window.clearInterval(poll);
  }, [proof]);
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
        setMessage("Something changed. Refreshing…");
        onRefresh(); return;
      }
      const payload = record(response.data);
      const code = typeof payload.code === "string" ? payload.code : "";
      const expires = typeof payload.expires_at === "string" ? utcTimestamp(payload.expires_at) : NaN;
      if (!response.response.ok || !/^[A-F0-9]{10}$/.test(code) || !Number.isFinite(expires) || expires <= Date.now()) {
        setMessage("We couldn't make a linking code. Refresh and try again."); return;
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
    } catch { setMessage("Telegram linking isn't working right now. Try again shortly."); }
    finally { setBusy(false); }
  }

  return <section className="ui-card" aria-labelledby="sr-telegram-title">
    <h2 id="sr-telegram-title">Telegram connection</h2>
    {state === "linked" ? <p role="status">Telegram is connected to this account. You do not need to link it again.</p>
      : state === "review" ? <p role="status">Telegram is linked. We&rsquo;re still joining your bot history to this account; you don&rsquo;t need to do anything.</p>
      : state === "unknown" ? <p>We couldn&rsquo;t check the link. Refresh before changing anything.</p>
      : <><p>{state === "pending" ? "Finish linking in Telegram." : "Link Telegram to get signals there too, with one account for both."}</p>
        {!proof && <button className="ui-btn" type="button" disabled={busy} onClick={requestLink}>
          {busy ? "Preparing code…" : state === "pending" ? "New code" : "Link Telegram"}</button>}
      </>}
    {proof && ["unlinked", "pending"].includes(state) && <div className="ui-form">
      <p>In the SignalRankAI bot, send <code>/link {proof.code}</code>. Keep this one-time code private.</p>
      <p>Expires {timeLabel(new Date(proof.expires).toISOString())}</p>
      {proof.href && <a className="ui-btn" href={proof.href} target="_blank" rel="noopener noreferrer">Open SignalRankAI in Telegram</a>}
      <p>Tap the button to open the bot and press Start, or send the code yourself. This page updates on its own once Telegram is linked.</p>
    </div>}
    <button className="ui-btn" type="button" disabled={busy} onClick={onRefresh}>Check again</button>
    {message && <p role="status">{message}</p>}
  </section>;
}
