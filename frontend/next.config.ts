import type { NextConfig } from "next";

/**
 * Browser account sessions are same-origin. A direct cross-origin API URL
 * cannot satisfy the sr_csrf double-submit cookie on the Next.js hostname.
 *
 * The server-only API destination must point to a trusted, dedicated backend,
 * with no path, userinfo, query or fragment. Never expose it as NEXT_PUBLIC_*.
 */
function canonicalApiOrigin(): string | null {
  const raw = String(process.env.SIGNALRANK_PLATFORM_API_ORIGIN || "").trim();
  if (!raw) return null;
  let url: URL;
  try { url = new URL(raw); }
  catch { throw new Error("SIGNALRANK_PLATFORM_API_ORIGIN must be an absolute URL"); }
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  const allowed = url.protocol === "https:" ||
    (process.env.NODE_ENV !== "production" && local && url.protocol === "http:");
  if (!allowed || url.username || url.password || url.search || url.hash ||
      (url.pathname !== "/" && url.pathname !== "")) {
    throw new Error("SIGNALRANK_PLATFORM_API_ORIGIN must be a trusted HTTPS origin without credentials, paths or query parameters");
  }
  return url.origin;
}

const origin = canonicalApiOrigin();
const privateHeaders = [
  { key: "Cache-Control", value: "private, no-store, max-age=0, must-revalidate" },
  { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive, nosnippet" },
  { key: "Referrer-Policy", value: "no-referrer" },
];
const nextConfig: NextConfig = {
  async headers() {
    return [
      { source: "/app", headers: privateHeaders },
      { source: "/app/:path*", headers: privateHeaders },
      { source: "/login", headers: privateHeaders },
      { source: "/recover", headers: privateHeaders },
      { source: "/magic-login", headers: privateHeaders },
      { source: "/api/v1/platform/:path*", headers: privateHeaders },
    ];
  },
  async rewrites() {
    // Missing origin is intentionally NOT replaced by an arbitrary public
    // backend. Requests remain same-origin and fail closed with 404.
    return origin
      ? [{ source: "/api/v1/platform/:path*", destination: `${origin}/api/v1/platform/:path*` }]
      : [];
  },
};

export default nextConfig;
