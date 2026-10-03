import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SignalRankAI · Trading Intelligence",
  description:
    "SignalRankAI trading intelligence, evidence review, paper trading and controlled connected-account workflows.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
