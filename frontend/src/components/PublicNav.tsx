import Link from "next/link";
import Image from "next/image";
import { ThemeControl } from "./ThemeControl";
import { ResponsiveDisclosure } from "./ResponsiveDisclosure";
import { WorkspaceLink } from "./WorkspaceLink";

const links = [
  ["Product","/product"],
  ["Markets","/markets"],
  ["Methodology","/methodology"],
  ["Risk","/risk"],
  ["Security","/security"],
  ["Plans","/pricing"],
] as const;

export function PublicNav({ current }: { current?: string }) {
  // The skip link targets #page-content, which every public page puts after this navigation.
  return <><a className="skip-link" href="#page-content">Skip to content</a><div className="mk-nav-wrap">
    <nav className="mk-container mk-nav" aria-label="Public site navigation">
      <Link className="brand-mark" href="/" aria-label="SignalRankAI home"><Image src="/brand/icon.svg" alt="" width={30} height={30} unoptimized /><span className="brand-word">SignalRank<span>AI</span></span></Link>
      <div className="mk-nav-links">{links.map(([label,href])=><Link key={href} href={href} aria-current={current===href?"page":undefined}>{label}</Link>)}</div>
      <div className="mk-nav-actions">
        <span className="mk-hide-mobile"><ThemeControl/></span>
        <WorkspaceLink className="ui-btn ui-btn--ghost mk-hide-mobile" href="/login">Sign in</WorkspaceLink>
        <WorkspaceLink className="ui-btn ui-btn--primary" href="/app">Open workspace</WorkspaceLink>
        <ResponsiveDisclosure className="mk-menu" label="Explore SignalRankAI" desktopFrom={1180}>
          <nav aria-label="Mobile public navigation">{links.map(([label,href])=><Link key={href} href={href}>{label}</Link>)}</nav>
          <div className="mk-menu-actions">
            <WorkspaceLink className="ui-btn ui-btn--lg" href="/login">Sign in</WorkspaceLink>
            <WorkspaceLink className="ui-btn ui-btn--primary ui-btn--lg" href="/app">Open workspace</WorkspaceLink>
            <ThemeControl/>
          </div>
        </ResponsiveDisclosure>
      </div>
    </nav>
  </div></>;
}
