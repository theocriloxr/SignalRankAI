import Link from "next/link";
import { ThemeControl } from "./ThemeControl";

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
        <Link className="brand" href="/"><img src="/brand/icon.svg" alt="" width="32" height="32" />SignalRank<span>AI</span></Link>
        <nav className="sideNav" aria-label="Workspace">
          {items.map(([label, href]) => (
            <Link key={href} href={href} aria-current={label.toLowerCase() === active.toLowerCase() ? "page" : undefined} className={label.toLowerCase() === active.toLowerCase() ? "active" : ""}>{label}</Link>
          ))}
        </nav>
        <ThemeControl />
      </aside>
      <section className="workspace">{children}</section>
    </div>
  );
}
