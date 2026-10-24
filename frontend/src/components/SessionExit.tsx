"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import client from "../lib/client";
import { Icon } from "./ui/Icon";

/** Server-confirmed sign-out. A failed logout is reported, never presented as success. */
export function SessionExit({ compact = false }: { compact?: boolean }) {
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
  return <div className="ws-signout">
    <button type="button" className={compact ? "ui-btn ui-btn--ghost ui-btn--sm" : "ui-btn ui-btn--ghost ui-btn--sm ui-btn--block"} onClick={signOut} disabled={busy}>
      <Icon name="logout"/>{busy?"Signing out…":"Sign out"}
    </button>
    {error&&<span role="alert" className="ui-muted">Sign-out could not be confirmed. Please retry.</span>}
  </div>;
}
