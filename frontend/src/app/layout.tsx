import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import "../styles/tokens.css";
import "../styles/base.css";
import "../styles/ui.css";
import "../styles/marketing.css";
import "../styles/workspace.css";

export const metadata: Metadata = {
  title: { default: "SignalRankAI — Multi-Asset Trading Intelligence", template: "%s · SignalRankAI" },
  description: "Evidence-driven multi-asset trading intelligence, paper trading, and broker-ready workflows.",
  applicationName: "SignalRankAI",
  icons: { icon: "/brand/icon.svg" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7f9" },
    { media: "(prefers-color-scheme: dark)", color: "#07090c" },
  ],
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Reading request headers keeps HTML dynamic so a nonce is never reused from a static page.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  // Apply the saved appearance before first paint so every page renders in the chosen theme.
  return <html lang="en" suppressHydrationWarning><head><script nonce={nonce} dangerouslySetInnerHTML={{ __html: `try{const theme=localStorage.getItem('signalrank.theme');if(theme==='dark'||theme==='light')document.documentElement.dataset.theme=theme}catch{}` }} /></head><body>{children}</body></html>;
}
