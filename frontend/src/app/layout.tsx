import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "SignalRankAI — Multi-Asset Trading Intelligence", template: "%s · SignalRankAI" },
  description: "Evidence-driven multi-asset trading intelligence, paper trading, and broker-ready workflows.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
