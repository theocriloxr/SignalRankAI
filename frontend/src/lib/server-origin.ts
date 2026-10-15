/** Trusted operator configuration only. Never take a proxy destination from a request. */
export function canonicalApiOrigin(raw = process.env.SIGNALRANK_PLATFORM_API_ORIGIN): string | null {
  if (!raw?.trim()) return null;
  let url: URL;
  try { url = new URL(raw.trim()); }
  catch { throw new Error("SIGNALRANK_PLATFORM_API_ORIGIN must be an absolute URL"); }
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (!(url.protocol === "https:" || (process.env.NODE_ENV !== "production" && local && url.protocol === "http:")) ||
      url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("SIGNALRANK_PLATFORM_API_ORIGIN must be a trusted HTTPS origin without credentials, paths or query parameters");
  }
  return url.origin;
}

export function workspaceMode(raw = process.env.SIGNALRANK_WORKSPACE_MODE): "next" | "legacy" {
  const mode = raw || "next";
  if (mode !== "next" && mode !== "legacy") throw new Error("SIGNALRANK_WORKSPACE_MODE must be next or legacy");
  return mode;
}

// These backend namespaces must survive a public-site cutover, including POST webhooks.
export const backendNamespaces = ["api", "app-assets", "activate", "billing", "webhook", "webhooks", "telegram",
  "paystack", "broker", "payout", "signals", "health", "healthz", "livez", "ready", "readyz", "version", "metrics", "diagnostics",
  "terms", "privacy", "cookies", "billing-policy", "risk-disclosure", "accessibility"];

export function backendOwnsPath(path: string, legacy: boolean): boolean {
  if (legacy && ["/login", "/recover", "/magic-login"].includes(path)) return true;
  if (legacy && path === "/retained-workspace") return true;
  if (legacy && (path === "/app" || path.startsWith("/app/"))) return true;
  return backendNamespaces.some(prefix => path === `/${prefix}` || path.startsWith(`/${prefix}/`));
}
