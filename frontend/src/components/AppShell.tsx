import Link from "next/link";
import Image from "next/image";
import { ThemeControl } from "./ThemeControl";
import { ResponsiveDisclosure } from "./ResponsiveDisclosure";
import { SessionExit } from "./SessionExit";
import { OperationsNavLink } from "./OperationsNavLink";
import { SiteCredit } from "./SiteCredit";
import { Icon, type IconName } from "./ui/Icon";

const groups = [
  { label:"Decisions",items:[["Overview","/app"],["Signals","/app/signals"],["Markets","/app/markets"],["Research","/app/research"],["Watchlists","/app/watchlists"],["Alerts","/app/alerts"],["Notifications","/app/notifications"]] },
  { label:"Portfolio",items:[["Paper","/app/paper"],["Portfolio","/app/portfolio"],["Performance","/app/performance"],["Journal","/app/journal"]] },
  { label:"Account & control",items:[["Brokers","/app/brokers"],["Billing","/app/billing"],["Support","/app/support"],["Settings","/app/settings"]] },
] as const;

const icons: Record<string, IconName> = {
  overview:"overview", signals:"signals", markets:"markets", research:"research", watchlists:"watchlists",
  alerts:"alerts", notifications:"notifications", paper:"paper", portfolio:"portfolio", performance:"performance",
  journal:"journal", brokers:"brokers", billing:"billing", support:"support", settings:"settings",
};
const tabs = [["Overview","/app"],["Signals","/app/signals"],["Paper","/app/paper"],["Portfolio","/app/portfolio"],["Brokers","/app/brokers"]] as const;

function groupOf(active: string): string {
  if (active === "Operations") return "Account & control";
  return groups.find(group => group.items.some(([label]) => label.toLowerCase() === active.toLowerCase()))?.label ?? "Workspace";
}

function Navigation({ active }: { active: string }) {
  return <>{groups.map(group=><section className="ws-nav-group" key={group.label} aria-label={group.label}>
    <h2>{group.label}</h2>
    {group.items.map(([label,href])=>{
      const current = label.toLowerCase()===active.toLowerCase();
      return <Link key={href} href={href} aria-current={current?"page":undefined}>
        <Icon name={icons[label.toLowerCase()]}/>{label}</Link>;
    })}
    {group.label==="Account & control"&&<OperationsNavLink active={active==="Operations"} />}
  </section>)}</>;
}

function Brand() {
  return <Link className="brand-mark" href="/" aria-label="SignalRankAI homepage">
    <Image src="/brand/icon.svg" alt="" width={30} height={30} unoptimized /><span className="brand-word">SignalRank<span>AI</span></span>
  </Link>;
}

/** Authenticated workspace frame. Navigation is presentation only: every section
 * still checks the session and entitlement on the server before any data renders. */
export function AppShell({ active, children }: { active: string; children: React.ReactNode }) {
  return <div className="ws-shell">
    <a className="skip-link" href="#ws-main">Skip to workspace content</a>
    <aside className="ws-sidebar" aria-label="Workspace">
      <div className="ws-sidebar-brand"><Brand/></div>
      <nav className="ws-nav" aria-label="Workspace navigation"><Navigation active={active}/></nav>
      <div className="ws-sidebar-foot">
        <div className="ws-foot-row"><span className="ui-eyebrow">Appearance</span><ThemeControl/></div>
        <SessionExit/>
        <Link href="/" className="ui-link">Public website <Icon name="external"/></Link>
      </div>
    </aside>
    <div className="ws-main">
      <header className="ws-topbar">
        <span className="ws-topbar-brand"><Brand/></span>
        <p className="ws-breadcrumb"><span>{groupOf(active)}</span><span aria-hidden="true">/</span><strong>{active}</strong></p>
        <div className="ws-topbar-actions">
          <span className="ws-topbar-theme"><ThemeControl/></span>
          <ResponsiveDisclosure className="ws-drawer" id="workspace-mobile-sections" label="Browse all workspace sections">
            <nav className="ws-nav" aria-label="All workspace sections"><Navigation active={active}/></nav>
            <div className="ws-sidebar-foot"><SessionExit/><Link href="/" className="ui-link">Public website <Icon name="external"/></Link></div>
          </ResponsiveDisclosure>
        </div>
      </header>
      <main className="ws-content" id="ws-main" tabIndex={-1}>{children}</main>
      <div className="ws-footer"><SiteCredit compact /></div>
    </div>
    <nav className="ws-tabbar" aria-label="Primary mobile workspace navigation">
      {tabs.map(([label,href])=><Link key={href} href={href} aria-current={active===label?"page":undefined}>
        <Icon name={icons[label.toLowerCase()]}/>{label}</Link>)}
    </nav>
  </div>;
}
