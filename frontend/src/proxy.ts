import { randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { backendOwnsPath, workspaceMode } from "./lib/server-origin";

export function proxy(request: NextRequest) {
  // The retained workspace owns its CSP and installed service worker. Applying a
  // Next nonce to its independent HTML would disable its scripts and lock users out.
  if (backendOwnsPath(request.nextUrl.pathname, workspaceMode() === "legacy")) {
    const response = NextResponse.next();
    if (!request.nextUrl.pathname.startsWith("/app-assets/")) {
      response.headers.set("Cache-Control", "private, no-store, max-age=0, must-revalidate");
      response.headers.set("X-Robots-Tag", "noindex, nofollow, noarchive, nosnippet");
    }
    return response;
  }
  const nonce = randomBytes(24).toString("base64");
  const development = process.env.NODE_ENV === "development";
  const policy = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    // React charts use inline style attributes; scripts remain nonce-only.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:", "font-src 'self'", "connect-src 'self'",
    "object-src 'none'", "base-uri 'none'", "form-action 'self'", "frame-ancestors 'none'",
  ].join("; ");
  const requestHeaders = new Headers(request.headers);
  // Always replace incoming nonce/CSP headers; a caller cannot choose our trust token.
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", policy);
  response.headers.set("Cache-Control", "private, no-store, max-age=0");
  return response;
}

export const config = {
  // API responses need the backend-path cache policy as well, including errors.
  matcher: ["/((?!_next/static/|_next/image|brand/|favicon.ico).*)"],
};
