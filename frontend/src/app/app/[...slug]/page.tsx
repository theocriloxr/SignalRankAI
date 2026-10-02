import { AppShell } from "../../../components/AppShell";

const copy: Record<string, { title: string; body: string }> = {
  signals: { title: "Signals", body: "Canonical delivered-signal feed with evidence, lifecycle status, freshness, risk, and channel receipts." },
  markets: { title: "Markets", body: "Multi-asset coverage, session state, provider health, and fresh-quote availability." },
  research: { title: "Research", body: "Strategy, regime, macro, news, and AI-assisted research kept distinct from execution truth." },
  watchlists: { title: "Watchlists", body: "Personal instruments and monitoring preferences synchronized with the unified account profile." },
  alerts: { title: "Alerts", body: "Price, market-state, provider, and signal alerts with durable notification history." },
  paper: { title: "Paper", body: "Durable paper account, positions, fills, fees, P&L, and signal-linked simulated execution." },
  portfolio: { title: "Portfolio", body: "Exposure, correlation, concentration, and risk-at-stop across tracked positions." },
  performance: { title: "Performance", body: "Forward performance separated from shadow, replay, and paper evidence." },
  journal: { title: "Journal", body: "Trade and decision journal connected to signal and outcome lifecycle evidence." },
  brokers: { title: "Brokers", body: "Broker connections and demo certification. Live eligibility stays blocked until all required checks pass." },
  billing: { title: "Billing", body: "Subscription status, receipts, entitlements, and idempotent payment reconciliation." },
  support: { title: "Support", body: "Support requests and account help with auditable status." },
  settings: { title: "Settings", body: "Profile, security, risk preferences, notification channels, sessions, and API access." },
  operations: { title: "Operations", body: "Owner-only release, provider, model, queue, database, and system-health cockpit." },
};

export default async function WorkspacePage({ params }: { params: Promise<{ slug: string[] }> }) {
  const { slug } = await params;
  const key = String(slug?.[0] || "overview").toLowerCase();
  const section = copy[key] || { title: "Workspace", body: "This workspace is part of the unified SignalRankAI platform." };
  return (
    <AppShell active={section.title}>
      <header className="workspaceHead"><div><p className="eyebrow">SignalRankAI</p><h1>{section.title}</h1></div><span className="statusPill">CANONICAL API</span></header>
      <div className="dashboardGrid">
        <article className="panel full"><h3>{section.title}</h3><p className="muted">{section.body}</p></article>
        <article className="panel"><h3>Data truth</h3><p className="small">Production surfaces use the typed backend API; stale or uncertified data does not become a tradable signal.</p></article>
        <article className="panel"><h3>Identity</h3><p className="small">Web, Telegram, mobile, paper, and broker workflows resolve to the same platform identity and entitlements.</p></article>
        <article className="panel"><h3>Auditability</h3><p className="small">Release SHA, signal provenance, delivery receipts, and execution evidence stay traceable.</p></article>
      </div>
    </AppShell>
  );
}
