import type { NextConfig } from "next";

/** The account workspace and email-reset token routes are never cacheable.
 * Browser cookies remain HttpOnly and are verified by the canonical API. */
const protectedHeaders = [
  { key:"Cache-Control", value:"private, no-store, max-age=0, must-revalidate" },
  { key:"X-Robots-Tag", value:"noindex, nofollow, noarchive, nosnippet" },
  { key:"Referrer-Policy", value:"no-referrer" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [
      { source:"/app", headers:protectedHeaders },
      { source:"/app/:path*", headers:protectedHeaders },
      { source:"/login", headers:protectedHeaders },
      { source:"/recover", headers:protectedHeaders },
      { source:"/magic-login", headers:protectedHeaders },
    ];
  },
};

export default nextConfig;
