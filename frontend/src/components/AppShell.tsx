import Link from "next/link";
import Image from "next/image";
import { ThemeControl } from "./ThemeControl";
import { ResponsiveDisclosure } from "./ResponsiveDisclosure";
import { SessionExit } from "./SessionExit";
import { OperationsNavLink } from "./OperationsNavLink";

const groups = [
  { label:"Decisions",items:[["Overview","/app"],["Signals","/app/signals"],["Markets","/app/markets"],["Research","/app/research"],["Watchlists","/app/watchlists"],["Alerts","/app/alerts"],["Notifications","/app/notifications"]] },
  { label:"Portfolio",items:[["Paper","/app/paper"],["Portfolio","/app/portfolio"],["Performance","/app/performance"],["Journal","/app/journal"]] },
  { label:"Account & control",items:[["Brokers","/app/brokers"],["Billing","/app/billing"],["Support","/app/support"],["Settings","/app/settings"]] },
] as const;

function Navigation({ active }: { active: string }) {
  return <>{groups.map(group=><section className="sr-nav-group" key={group.label}>
    <h2>{group.label}</h2>
    {group.items.map(([label,href])=><Link key={href} href={href}
      aria-current={label.toLowerCase()===active.toLowerCase()?"page":undefined}
      className={label.toLowerCase()===active.toLowerCase()?"active":undefined}>{label}</Link>)}
    {group.label==="Account & control"&&<OperationsNavLink active={active==="Operations"} />}
  </section>)}</>;
}

export function AppShell({ active, children }: { active: string; children: React.ReactNode }) {
  return <div className="appShell sr-app-shell">
    <a className="sr-skip-link" href="#sr-main">Skip to workspace content</a>
    <aside className="sidebar sr-sidebar">
      <Link className="brand" href="/" aria-label="SignalRankAI homepage">
        <Image src="/brand/icon.svg" alt="" width={32} height={32} unoptimized />SignalRank<span>AI</span>
      </Link>
      <p className="sr-sidebar-caption">TRADING INTELLIGENCE / PRIVATE WORKSPACE</p>
      <nav className="sideNav sr-desktop-nav" aria-label="Desktop workspace navigation"><Navigation active={active}/></nav>
      <ResponsiveDisclosure className="sr-mobile-drawer" id="workspace-mobile-sections" label="Browse all workspace sections"><nav aria-label="All mobile workspace sections"><Navigation active={active}/></nav></ResponsiveDisclosure>
      <div className="sr-sidebar-foot"><ThemeControl/><SessionExit/><Link href="/" className="sr-secondary-link">Public website ↗</Link></div>
    </aside>
    <main className="workspace" id="sr-main">{children}</main>
    <nav className="sr-bottom-tabs" aria-label="Primary mobile workspace navigation">
      <Link href="/app" aria-current={active==="Overview"?"page":undefined}>Overview</Link>
      <Link href="/app/signals" aria-current={active==="Signals"?"page":undefined}>Signals</Link>
      <Link href="/app/paper" aria-current={active==="Paper"?"page":undefined}>Paper</Link>
      <Link href="/app/portfolio" aria-current={active==="Portfolio"?"page":undefined}>Portfolio</Link>
      <Link href="/app/brokers" aria-current={active==="Brokers"?"page":undefined}>Brokers</Link>
    </nav>
  </div>;
}
