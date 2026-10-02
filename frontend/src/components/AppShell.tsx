import Link from "next/link";

const items = [
  ["Overview", "/app"],
  ["Signals", "/app/signals"],
  ["Markets", "/app/markets"],
  ["Research", "/app/research"],
  ["Watchlists", "/app/watchlists"],
  ["Alerts", "/app/alerts"],
  ["Paper", "/app/paper"],
  ["Portfolio", "/app/portfolio"],
  ["Performance", "/app/performance"],
  ["Journal", "/app/journal"],
  ["Brokers", "/app/brokers"],
  ["Billing", "/app/billing"],
  ["Support", "/app/support"],
  ["Settings", "/app/settings"],
  ["Operations", "/app/operations"],
];

export function AppShell({ active, children }: { active: string; children: React.ReactNode }) {
  return (
    <div className="appShell">
      <aside className="sidebar">
        <Link className="brand" href="/">SignalRank<span>AI</span></Link>
        <nav className="sideNav">
          {items.map(([label, href]) => (
            <Link key={href} href={href} className={label.toLowerCase() === active.toLowerCase() ? "active" : ""}>{label}</Link>
          ))}
        </nav>
      </aside>
      <section className="workspace">{children}</section>
    </div>
  );
}
