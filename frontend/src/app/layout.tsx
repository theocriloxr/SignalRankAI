import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "../styles/tokens.css";
import "../styles/base.css";
import "../styles/ui.css";
import "../styles/marketing.css";
import "../styles/workspace.css";

export const metadata: Metadata = {
  title: { default: "SignalRankAI — Multi-Asset Trading Intelligence", template: "%s · SignalRankAI" },
  description: "Evidence-driven multi-asset trading intelligence, paper trading, and broker-ready workflows.",
  applicationName: "SignalRankAI",
  // The real SignalRank mark everywhere a browser or phone shows an icon. Until
  // 8 Nov 2026 /favicon.ico was the stock Next.js icon, which browser tabs used.
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "48x48" },
      { url: "/brand/icon-32.png", type: "image/png", sizes: "32x32" },
      { url: "/brand/icon-192.png", type: "image/png", sizes: "192x192" },
      { url: "/brand/icon.svg", type: "image/svg+xml" },
    ],
    shortcut: "/favicon.ico",
    apple: [{ url: "/brand/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f3ec" },
    { media: "(prefers-color-scheme: dark)", color: "#161512" },
  ],
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Reading request headers keeps HTML dynamic so a nonce is never reused from a static page.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  // Apply the saved appearance before first paint so every page renders in the chosen theme.
  return <html lang="en" suppressHydrationWarning><head><script nonce={nonce} dangerouslySetInnerHTML={{ __html: `try{const theme=localStorage.getItem('signalrank.theme');if(theme==='dark'||theme==='light')document.documentElement.dataset.theme=theme}catch{}` }} /></head><body>{children}</body></html>;
}
