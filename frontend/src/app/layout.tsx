import type { Metadata } from "next";
import "./globals.css";
import "./workspace-design.css";

export const metadata: Metadata = {
  title: { default: "SignalRankAI — Multi-Asset Trading Intelligence", template: "%s · SignalRankAI" },
  description: "Evidence-driven multi-asset trading intelligence, paper trading, and broker-ready workflows.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: `try{const theme=localStorage.getItem('signalrank.theme');if(theme==='dark'||theme==='light')document.documentElement.dataset.theme=theme}catch{}` }} /></head><body>{children}</body></html>;
}
