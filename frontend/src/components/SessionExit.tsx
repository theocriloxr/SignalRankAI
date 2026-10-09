"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import client from "../lib/client";

export function SessionExit() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function signOut() {
    if (busy) return;
    setBusy(true);setError(false);
    try {
      const result = await client.POST("/api/v1/platform/auth/logout");
      if (result.response.ok) { router.replace("/login"); router.refresh(); return; }
    } catch { /* Keep user in place; never misrepresent a failed logout. */ }
    setError(true);setBusy(false);
  }
  return <div className="sr-exit"><button type="button" onClick={signOut} disabled={busy}>{busy?"Signing out…":"Sign out securely"}</button>{error&&<span role="alert">Sign-out could not be confirmed. Please retry.</span>}</div>;
}
