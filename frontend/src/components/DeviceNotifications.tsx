"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import client from "../lib/client";

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

/** App notifications on this device and installing the app (owner request, 8 Nov 2026).
 * Push carries only the title and a short line; full, tier-limited detail opens in the app. */
const noSubscribe = () => () => {};
/** "push|standalone|ios" from the browser; "" while rendering on the server. */
function browserCapabilities(): string {
  const push = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const standalone = window.matchMedia("(display-mode: standalone)").matches;
  return `${push ? 1 : 0}|${standalone ? 1 : 0}|${/iphone|ipad|ipod/i.test(navigator.userAgent) ? 1 : 0}`;
}

export function DeviceNotifications() {
  const caps = useSyncExternalStore(noSubscribe, browserCapabilities, () => "");
  const [pushOk, standaloneFlag, iosFlag] = caps ? caps.split("|") : ["", "", ""];
  const [registrationFailed, setRegistrationFailed] = useState(false);
  const supported: boolean | null = caps ? pushOk === "1" && !registrationFailed : null;
  const standalone = standaloneFlag === "1";
  const ios = iosFlag === "1";
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [install, setInstall] = useState<InstallEvent | null>(null);

  useEffect(() => {
    const ok = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
    const onPrompt = (event: Event) => { event.preventDefault(); setInstall(event as InstallEvent); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    if (ok) {
      navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" })
        .then(reg => reg.pushManager.getSubscription())
        .then(sub => setSubscribed(Boolean(sub)))
        .catch(() => setRegistrationFailed(true));
    }
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  async function enable() {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") { setMessage("Notifications are blocked for this site in your browser settings."); return; }
      const key = await client.GET("/api/v1/platform/push/vapid-public-key");
      const publicKey = key.data && typeof (key.data as { public_key?: unknown }).public_key === "string"
        ? (key.data as { public_key: string }).public_key : "";
      if (!publicKey) { setMessage("App notifications aren't available right now."); return; }
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription()
        ?? await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) });
      const saved = await client.POST("/api/v1/platform/push-devices", { body: {
        provider: "webpush", push_token: JSON.stringify(subscription.toJSON()), platform: "web",
        device_id: navigator.userAgent.slice(0, 64), app_version: "web",
      } });
      if (!saved.response.ok) { setMessage("This device couldn't be registered. Try again."); return; }
      await client.PUT("/api/v1/platform/notifications/preferences", { body: { push_enabled: true } });
      setSubscribed(true);
      setMessage("Notifications are on for this device.");
    } catch {
      setMessage("This browser couldn't turn on notifications.");
    } finally { setBusy(false); }
  }

  async function disable() {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      await subscription?.unsubscribe();
      setSubscribed(false);
      setMessage("Notifications are off for this device.");
    } catch { setMessage("That didn't work. Try again."); } finally { setBusy(false); }
  }

  return <section className="ui-card" aria-labelledby="sr-device-notifications">
    <h2 id="sr-device-notifications">This device</h2>
    <p>Get a notification on this phone or computer when a signal is sent to you or one of your trades changes. Full detail, as your plan allows, opens in the app.</p>
    {supported === false && <p className="ui-muted">{ios && !standalone
      ? "On iPhone and iPad, add SignalRankAI to your Home Screen first (Share → Add to Home Screen), then open it from there."
      : "This browser doesn't support app notifications."}</p>}
    {supported && <div className="ui-form-row">
      {subscribed
        ? <button type="button" className="ui-btn" onClick={disable} disabled={busy}>Turn off on this device</button>
        : <button type="button" className="ui-btn ui-btn--primary" onClick={enable} disabled={busy}>{busy ? "Turning on…" : "Turn on notifications"}</button>}
    </div>}
    {!standalone && (install
      ? <p><button type="button" className="ui-btn" onClick={async () => { await install.prompt(); setInstall(null); }}>Install the SignalRankAI app</button></p>
      : <p className="ui-muted">To install the app: in Chrome or Edge use the install icon in the address bar; on iPhone use Share → Add to Home Screen; on Android use the browser menu → Install app.</p>)}
    {message && <p className="ui-feedback" role="status">{message}</p>}
  </section>;
}
