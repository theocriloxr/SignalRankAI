import { canonicalApiOrigin, workspaceMode } from "../../lib/server-origin";

export const dynamic = "force-dynamic";

/** Retain the existing HTML shell with an explicit private response policy.
 * APIs, credentials, mutations and assets continue through their canonical paths.
 */
export async function GET() {
  const headers = {"Cache-Control":"private, no-store, max-age=0, must-revalidate",
    "X-Robots-Tag":"noindex, nofollow, noarchive, nosnippet", "Referrer-Policy":"no-referrer"};
  if (workspaceMode() !== "legacy") return new Response("Not found",{status:404,headers});
  const origin = canonicalApiOrigin();
  if (!origin) return new Response("Workspace connection unavailable. Please retry shortly.",{status:503,headers});
  try {
    // The upstream /app is an identity-free static shell. Do not send cookies or
    // auth headers on this fetch; its browser requests retain their own sessions.
    const upstream = await fetch(origin+"/app",{cache:"no-store",redirect:"error",signal:AbortSignal.timeout(10000),
      headers:{Accept:"text/html"}});
    if (!upstream.ok || !upstream.headers.get("content-type")?.includes("text/html")) {
      return new Response("Workspace connection unavailable. Please retry shortly.",{status:503,headers});
    }
    const response = new Response(upstream.body,{headers:{...headers,"Content-Type":"text/html; charset=utf-8"}});
    // Preserve any stricter policy from the owner of this separate HTML document.
    response.headers.set("Content-Security-Policy",upstream.headers.get("content-security-policy") ||
      "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
    return response;
  } catch { return new Response("Workspace connection unavailable. Please retry shortly.",{status:503,headers}); }
}
