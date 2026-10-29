import { createHmac } from "node:crypto";
import { isIP } from "node:net";
import { canonicalApiOrigin } from "./server-origin.ts";

const privateHeaders = {"Cache-Control":"private, no-store, max-age=0, must-revalidate",
  "X-Robots-Tag":"noindex, nofollow, noarchive, nosnippet", "Referrer-Policy":"no-referrer",
  "X-Content-Type-Options":"nosniff"};
// Never the browser's own x-forwarded-for/x-real-ip: the backend must not trust client-chosen addresses.
const requestHeaders = ["accept", "content-type", "authorization", "cookie", "origin", "referer",
  "x-csrf-token", "idempotency-key", "if-match", "if-none-match", "x-request-id", "user-agent"];

/** Pass on the address the hosting edge saw (x-real-ip), signed when a shared secret is configured.
 * The signature survives a second trip through the public edge, which would replace x-real-ip
 * with this server's own address and put every web user in one rate-limit bucket. */
function forwardClientAddress(request: Request, headers: Headers): void {
  const address = (request.headers.get("x-real-ip") || "").trim();
  if (!isIP(address)) return;
  headers.set("x-real-ip", address);
  const secret = process.env.SIGNALRANK_CLIENT_IP_SECRET || "";
  if (secret.length < 32) return;
  const timestamp = String(Math.floor(Date.now() / 1000));
  headers.set("x-signalrank-client-ip", address);
  headers.set("x-signalrank-client-ip-ts", timestamp);
  headers.set("x-signalrank-client-ip-signature", createHmac("sha256", secret).update(`${address}.${timestamp}`).digest("hex"));
}
const hopHeaders = ["connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailer", "transfer-encoding", "upgrade", "content-length", "content-encoding"];

/** One canonical request, no retries or redirect following; backend owns authorization. */
export async function proxyPlatformRequest(request: Request, send: typeof fetch = fetch): Promise<Response> {
  let origin: string | null;
  try { origin = canonicalApiOrigin(); } catch { origin = null; }
  if (!origin) return Response.json({detail:"Account service unavailable."},{status:503,headers:privateHeaders});
  const incoming = new URL(request.url);
  if ((incoming.pathname !== "/api/v1/platform" && !incoming.pathname.startsWith("/api/v1/platform/")) ||
      /%(?:2f|5c|00|25)/i.test(incoming.pathname)) {
    return Response.json({detail:"Not found."},{status:404,headers:privateHeaders});
  }
  const destination = new URL(origin);
  destination.pathname = incoming.pathname;
  destination.search = incoming.search;
  const headers = new Headers();
  for (const name of requestHeaders) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name,value);
  }
  headers.set("accept-encoding","identity");
  forwardClientAddress(request, headers);
  // This host is only metadata. It can never choose the fixed destination.
  headers.set("x-forwarded-host",incoming.host);
  const method = request.method;
  const options: RequestInit & {duplex?: "half"} = {method,headers,cache:"no-store",redirect:"manual",
    signal:AbortSignal.any([request.signal,AbortSignal.timeout(30000)])};
  if (method !== "GET" && method !== "HEAD" && request.body) {
    options.body=request.body;
    options.duplex="half";
  }
  try {
    const upstream = await send(destination,options);
    const output = new Headers(upstream.headers);
    const connectionTokens = (output.get("connection") || "").split(",").map(name=>name.trim()).filter(Boolean);
    for (const name of [...hopHeaders,...connectionTokens]) output.delete(name);
    // Keep refresh/login's separate cookies; a comma-joined value corrupts expiry dates.
    output.delete("set-cookie");
    for (const cookie of upstream.headers.getSetCookie()) output.append("set-cookie",cookie);
    for (const [name,value] of Object.entries(privateHeaders)) output.set(name,value);
    const vary = new Set((output.get("vary") || "").split(",").map(x=>x.trim()).filter(Boolean));
    if (!vary.has("*")) {vary.add("Cookie");vary.add("Authorization");}
    output.set("vary",[...vary].join(", "));
    return new Response(method === "HEAD" || [204,304].includes(upstream.status) ? null : upstream.body,
      {status:upstream.status,statusText:upstream.statusText,headers:output});
  } catch {
    return Response.json({detail:"Account service temporarily unavailable."},{status:502,headers:privateHeaders});
  }
}
