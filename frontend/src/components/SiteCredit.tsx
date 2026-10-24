import Link from "next/link";
import Image from "next/image";

const directory = [
  { heading: "Product", links: [["Overview","product"],["Features","features"],["Markets","markets"],["Strategies","strategies"],["AI evaluation","ai"],["Plans","pricing"]] },
  { heading: "Trust", links: [["Methodology","methodology"],["Risk","risk"],["Security","security"],["Privacy","privacy"],["Data providers","providers"]] },
  { heading: "Help", links: [["Documentation","docs"],["FAQ","faq"],["Platform status","status"],["Contact and support","contact"]] },
] as const;

/** Shared footer with the CRILOX Solutions attribution on every public and private shell. */
export function SiteCredit({compact=false,navigation=false}:{compact?:boolean;navigation?:boolean}) {
  return <footer className={compact ? "site-footer site-footer--compact" : "site-footer"}>
    {navigation && <div className="site-footer-top">
      <div className="site-footer-brand">
        <Link className="brand-mark" href="/" aria-label="SignalRankAI home"><Image src="/brand/icon.svg" alt="" width={30} height={30} unoptimized /><span className="brand-word">SignalRank<span>AI</span></span></Link>
        <p>Multi-asset trading intelligence with evidence, explicit rejection and risk-aware account workflows.</p>
      </div>
      <nav className="site-footer-directory" aria-label="Product and help pages">
        {directory.map(group => <div key={group.heading}>
          <h2>{group.heading}</h2>
          <ul>{group.links.map(([name,path]) => <li key={path}><Link href={`/${path}`}>{name}</Link></li>)}</ul>
        </div>)}
      </nav>
    </div>}
    <div className="site-footer-bottom">
      <span>© SignalRankAI · Decision intelligence. Trading involves risk of loss.</span>
      <span className="site-footer-links">
        <Link href="/risk">Risk disclosure</Link>
        <span>Powered by <a href="https://www.criloxsolutions.com" target="_blank" rel="noopener noreferrer"
          aria-label="CRILOX Solutions — opens in a new tab">CRILOX Solutions <span aria-hidden="true">↗</span></a></span>
      </span>
    </div>
  </footer>;
}
