import Link from "next/link";
import Image from "next/image";
import { ThemeControl } from "./ThemeControl";

const links = [
  ["Methodology","/methodology"],
  ["Risk","/risk"],
  ["Security","/security"],
  ["Providers","/providers"],
  ["Documentation","/docs"],
] as const;

export function PublicNav() {
  return <nav className="topbar sr-public-nav" aria-label="Public site navigation">
    <Link className="brand" href="/" aria-label="SignalRankAI home"><Image src="/brand/icon.svg" alt="" width={32} height={32} unoptimized />SignalRank<span>AI</span></Link>
    <div className="sr-public-links">{links.map(([label,href])=><Link key={href} href={href}>{label}</Link>)}</div>
    <ThemeControl/>
    <Link className="button secondary" href="/login">Sign in</Link>
    <Link className="button" href="/app">Workspace</Link>
    <details className="sr-public-mobile-menu"><summary>Explore</summary>
      <div>{links.map(([label,href])=><Link key={href} href={href}>{label}</Link>)}
        <Link href="/login">Sign in</Link><Link href="/app">Workspace</Link></div>
    </details>
  </nav>;
}
