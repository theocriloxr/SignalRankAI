/** Restrict post-auth navigation to local workspace routes. Never trust a URL from a query string. */
export function safeReturnPath(value: string | null): string {
  if (!value || value.length > 2048 || /[\\\u0000-\u0020]/.test(value)) return "/app";
  try {
    const url = new URL(value, "https://workspace.invalid");
    if (!value.startsWith("/") || url.origin !== "https://workspace.invalid" ||
        (url.pathname !== "/app" && !url.pathname.startsWith("/app/"))) return "/app";
    return url.pathname + url.search + url.hash;
  } catch { return "/app"; }
}
