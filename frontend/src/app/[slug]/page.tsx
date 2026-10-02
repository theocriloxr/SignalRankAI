import Link from "next/link";
import { notFound } from "next/navigation";

const pages: Record<string, { title: string; eyebrow: string; paragraphs: string[] }> = {
  pricing: { title: "Pricing", eyebrow: "Plans", paragraphs: ["Entitlements control signal detail, analytics, delivery timing, paper features, and professional tooling. Billing status never bypasses quality or risk gates.", "Live execution, when eventually enabled for an account, requires separate technical and account certification."] },
  methodology: { title: "Methodology", eyebrow: "How SignalRankAI works", paragraphs: ["Candidates move through market-data certification, strategy logic, consensus, scoring, ML calibration, risk, liquidity, session, and delivery gates.", "A candidate rejected at any critical stage remains a rejection. Signal frequency is never a reason to weaken a gate."] },
  risk: { title: "Risk", eyebrow: "Fail closed", paragraphs: ["Trading involves loss risk. SignalRankAI is designed to reduce software and data uncertainty, not remove market uncertainty.", "Stale data, ambiguous symbols, uncertified broker state, breached portfolio limits, or an active kill switch must block execution."] },
  security: { title: "Security", eyebrow: "Account and execution safety", paragraphs: ["Sensitive broker and API credentials are handled separately from ordinary profile data. Withdrawal permissions are not required for trading integrations.", "Security-sensitive changes require stronger authentication, auditing, and explicit user intent."] },
  status: { title: "Status", eyebrow: "System health", paragraphs: ["Operational status is derived from service readiness, provider health, database and queue health, model state, and delivery telemetry.", "A process being alive is not the same as being ready for trading."] },
  docs: { title: "Documentation", eyebrow: "Product reference", paragraphs: ["SignalRankAI exposes typed APIs and unified workflows for signals, markets, paper trading, broker connections, notifications, account settings, and operations.", "Release and signal evidence should always identify the exact code and model versions involved."] },
  providers: { title: "Market-data providers", eyebrow: "Source lineage", paragraphs: ["Provider routing is asset-class and capability aware. Every execution-sensitive quote must satisfy freshness, identity, and source-quality rules.", "Fallbacks are explicit and observable; missing certified data should result in no trade rather than fabricated continuity."] },
};

export function generateStaticParams() { return Object.keys(pages).map((slug) => ({ slug })); }

export default async function PublicPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const page = pages[slug];
  if (!page) notFound();
  return (
    <main><section className="hero">
      <nav className="topbar"><Link className="brand" href="/">SignalRank<span>AI</span></Link><Link className="button secondary" href="/app">Open platform</Link></nav>
      <div style={{ padding: "92px 0", maxWidth: 800 }}>
        <p className="eyebrow">{page.eyebrow}</p><h1 style={{ fontSize: "clamp(44px,7vw,78px)" }}>{page.title}</h1>
        {page.paragraphs.map((p) => <p className="lede" key={p}>{p}</p>)}
      </div>
    </section></main>
  );
}
