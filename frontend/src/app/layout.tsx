import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";
import "./workspace-design.css";
import "./public-design.css";
import "./cinematic.css";

export const metadata: Metadata = {
  title: { default: "SignalRankAI — Multi-Asset Trading Intelligence", template: "%s · SignalRankAI" },
  description: "Evidence-driven multi-asset trading intelligence, paper trading, and broker-ready workflows.",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Reading request headers keeps HTML dynamic so a nonce is never reused from a static page.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return <html lang="en" suppressHydrationWarning><head><script nonce={nonce} dangerouslySetInnerHTML={{ __html: `try{const theme=localStorage.getItem('signalrank.theme');if(theme==='dark'||theme==='light')document.documentElement.dataset.theme=theme}catch{}` }} /></head><body>{children}</body></html>;
}
