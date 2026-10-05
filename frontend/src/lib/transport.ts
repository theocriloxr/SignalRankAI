/** Browser transport for the canonical cookie-authenticated platform API. */
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function csrfCookie(cookie: string): string | null {
  const value = cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("sr_csrf="));
  if (!value) return null;
  try { return decodeURIComponent(value.slice("sr_csrf=".length)) || null; }
  catch { return null; }
}

export async function platformFetch(input: Request): Promise<Response> {
  const headers = new Headers(input.headers);
  if (!SAFE_METHODS.has(input.method.toUpperCase()) && typeof document !== "undefined") {
    const proof = csrfCookie(document.cookie);
    if (proof) headers.set("X-CSRF-Token", proof);
  }
  // Keep the original body, cancellation signal and headers. Cookie sessions
  // require credentials on both reads and writes; HttpOnly tokens stay outside
  // JavaScript storage and never become a fabricated bearer identity.
  return fetch(new Request(input, {credentials: "include", headers}));
}
