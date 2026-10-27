import type { NextConfig } from "next";
import { backendNamespaces, canonicalApiOrigin, workspaceMode } from "./src/lib/server-origin";

/**
 * Browser account sessions are same-origin. A direct cross-origin API URL
 * cannot satisfy the sr_csrf double-submit cookie on the Next.js hostname.
 *
 * The server-only API destination must point to a trusted, dedicated backend,
 * with no path, userinfo, query or fragment. Never expose it as NEXT_PUBLIC_*.
 */
const origin = canonicalApiOrigin();
const mode = workspaceMode();
if (mode === "legacy" && !origin) throw new Error("Retaining the existing workspace requires a trusted backend origin");
const legacyViews: Record<string,string> = {signals:"signals", markets:"markets", research:"tools",
  watchlists:"markets", alerts:"account", notifications:"overview", paper:"paper", portfolio:"portfolio",
  performance:"performance", journal:"journal", brokers:"account", billing:"account", support:"support",
  settings:"account", operations:"ops"};
const privateHeaders = [
  { key: "Cache-Control", value: "private, no-store, max-age=0, must-revalidate" },
  { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive, nosnippet" },
  { key: "Referrer-Policy", value: "no-referrer" },
];
const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  env: { SIGNALRANK_WORKSPACE_MODE: mode },
  async redirects() {
    if (mode !== "legacy") return [];
    // The retained SPA reads the visible URL. An upstream-only query rewrite
    // would lose the requested view and send every deep link to its default page.
    return [
      ...Object.entries(legacyViews).map(([page,view]) => ({
        source:`/app/${page}`, destination:`/app?view=${view}`, permanent:false,
      })),
      ...["login","recover","magic-login"].map(page => ({source:`/${page}`,destination:"/app",permanent:false})),
    ];
  },
  async headers() {
    return [
      { source: "/:path*", headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      ] },
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
    if (!origin) return [];
    const beforeFiles = backendNamespaces.filter(prefix=>prefix !== "api").map(prefix => ({
      source: `/${prefix}/:path*`, destination: `${origin}/${prefix}/:path*`,
    }));
    if (mode === "legacy") {
      // Preserve the installed PWA and mature account/owner workflows until parity is verified.
      beforeFiles.push({source:"/app/service-worker.js", destination:`${origin}/app/service-worker.js`},
        {source:"/app/manifest.webmanifest", destination:`${origin}/app/manifest.webmanifest`});
      beforeFiles.push({source:"/app",destination:"/retained-workspace"});
      beforeFiles.push({source:"/app/:path*",destination:"/retained-workspace"});
    }
    // The canonical account Route Handler enforces private response headers.
    // All other backend APIs retain their existing transparent rewrite.
    return {beforeFiles, afterFiles:[], fallback:[{source:"/api/:path*",destination:`${origin}/api/:path*`}]};
  },
};

export default nextConfig;
