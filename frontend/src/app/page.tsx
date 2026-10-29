import Link from "next/link";
import { PublicNav } from "../components/PublicNav";
import { SignalLifecycleExperience } from "../components/SignalLifecycleExperience";
import { SiteCredit } from "../components/SiteCredit";
import { WorkspaceLink } from "../components/WorkspaceLink";
import { Icon, type IconName } from "../components/ui/Icon";

const markets = [
  { code:"CRYPTO", name:"Crypto", copy:"Continuous markets with exchange-specific symbols and venue rules." },
  { code:"FOREX", name:"Forex", copy:"Session-aware currency pairs with broker-specific contract sizes." },
  { code:"INDICES", name:"Indices", copy:"Cash and derivative index exposure kept as distinct instruments." },
  { code:"STOCKS", name:"Equities", copy:"Exchange sessions, holidays and corporate events respected." },
  { code:"COMMODITIES", name:"Commodities", copy:"Metals and energy with explicit contract and spread checks." },
];

const features: { icon: IconName; title: string; copy: string; href: string; cta: string }[] = [
  { icon:"signals", title:"Signal intelligence", copy:"Filter delivered decisions by market, strategy and timeframe, then open the evidence behind each one.", href:"/app/signals", cta:"Explore signals" },
  { icon:"paper", title:"Paper desk", copy:"Practise with simulated positions, cash and P&L that are always kept apart from live broker balances.", href:"/app/paper", cta:"Explore paper trading" },
  { icon:"brokers", title:"Broker oversight", copy:"Review each linked account, its verified environment and its permissions. A connection alone never approves a trade.", href:"/app/brokers", cta:"Inspect connections" },
  { icon:"markets", title:"Market directory", copy:"Search the canonical instrument registry with provider lineage, tick size and quantity steps.", href:"/app/markets", cta:"Browse markets" },
  { icon:"performance", title:"Performance evidence", copy:"Outcome-based results with sample sizes and disclosure, never a headline win rate on its own.", href:"/app/performance", cta:"View performance" },
  { icon:"telegram", title:"Web and Telegram", copy:"One account, one entitlement model and one signal history across the web workspace and Telegram.", href:"/app/settings", cta:"Link Telegram" },
];

const proof: { icon: IconName; label: string }[] = [
  { icon:"shield", label:"Server-side risk gates" },
  { icon:"check", label:"Receipt-backed signals" },
  { icon:"paper", label:"Paper is never presented as live" },
];

export default function Home() {
  return <main className="mk-page">
    <PublicNav/>
    <section className="mk-hero skip-target" id="page-content" tabIndex={-1} aria-labelledby="mk-hero-title">
      <div className="mk-container mk-hero-grid">
        <div className="mk-hero-copy">
          <span className="mk-pill"><b>EVIDENCE FIRST</b> Multi-asset trading intelligence</span>
          <h1 id="mk-hero-title">Read the market.<br/>Question the signal.<br/><em>Own the decision.</em></h1>
          <p className="mk-lede">SignalRankAI connects market research, quality gates, signal evidence and risk-aware account workflows across crypto, forex, indices, equities and commodities — on the web and through Telegram.</p>
          <div className="mk-hero-actions">
            <WorkspaceLink href="/login" className="ui-btn ui-btn--primary ui-btn--lg">Get started <Icon name="arrowRight"/></WorkspaceLink>
            <Link href="#lifecycle" className="ui-btn ui-btn--lg">See how decisions are made</Link>
          </div>
          <div className="mk-proof">{proof.map(item=><span key={item.label}><Icon name={item.icon}/>{item.label}</span>)}</div>
        </div>
        <div className="mk-schematic" role="img" aria-label="Schematic of the SignalRankAI decision pipeline. This is a system illustration: no market data, prices, balances or performance figures are shown.">
          <div className="mk-schematic-bar" aria-hidden="true"><span><i/><i/><i/></span><strong>DECISION PIPELINE</strong><span className="ui-badge ui-badge--warning">SCHEMATIC / NOT LIVE</span></div>
          <div className="mk-schematic-body" aria-hidden="true">
            <div className="mk-gate"><span><Icon name="database"/></span><div><strong>Data quality</strong><small>Source, session and quote freshness</small></div><span className="ui-badge ui-badge--positive ui-badge--plain">Check</span></div>
            <div className="mk-gate"><span><Icon name="research"/></span><div><strong>Strategy consensus</strong><small>Setup, regime and model calibration</small></div><span className="ui-badge ui-badge--info ui-badge--plain">Review</span></div>
            <div className="mk-gate"><span><Icon name="shield"/></span><div><strong>Risk admission</strong><small>Account limits, exposure and permissions</small></div><span className="ui-badge ui-badge--warning ui-badge--plain">Enforce</span></div>
            <div className="mk-gate-bars"><span>ENTRY</span><span>STOP</span><span>TARGET</span></div>
          </div>
          <div className="mk-schematic-foot" aria-hidden="true"><span>WEAK EVIDENCE IS REJECTED</span><span>NO AUTO-TRADE CLAIM</span></div>
        </div>
      </div>
    </section>

    <section className="mk-section mk-section--tight" aria-labelledby="mk-markets-title">
      <div className="mk-container">
        <div className="mk-section-head"><p className="ui-eyebrow ui-eyebrow--brand">One intelligence layer</p><h2 id="mk-markets-title">Five market families. <em>One canonical registry.</em></h2>
          <p>Every instrument is identified before it is compared, so similar names on different venues are never confused.</p></div>
        <div className="mk-markets">{markets.map(m=><div className="mk-market" key={m.code}><span className="mono">{m.code}</span><strong>{m.name}</strong><small>{m.copy}</small></div>)}</div>
      </div>
    </section>

    <section className="mk-section" aria-labelledby="mk-standard-title">
      <div className="mk-container mk-statement">
        <div><p className="ui-eyebrow ui-eyebrow--brand">The SignalRank standard</p><h2 id="mk-standard-title">The best decision is sometimes <em>no trade.</em></h2></div>
        <div><p>More alerts do not mean better intelligence. SignalRankAI is built around evidence, explicit rejection, and the difference between an observed opportunity, a simulated paper result and an executed broker order.</p>
          <Link className="ui-link" href="/methodology">Read the methodology <Icon name="arrowRight"/></Link></div>
      </div>
    </section>

    <SignalLifecycleExperience/>

    <section className="mk-section" aria-labelledby="mk-features-title">
      <div className="mk-container">
        <div className="mk-section-head"><p className="ui-eyebrow ui-eyebrow--brand">Your workspace, connected</p><h2 id="mk-features-title">From the first scan to the full picture.</h2>
          <p>One secure workspace for the signal lifecycle. Data and access always come from your authenticated account, never from this page.</p></div>
        <div className="mk-features">{features.map(f=><WorkspaceLink key={f.href} href={f.href} className="mk-feature">
          <span className="mk-feature-icon"><Icon name={f.icon}/></span><h3>{f.title}</h3><p>{f.copy}</p>
          <span className="ui-link">{f.cta} <Icon name="arrowRight"/></span>
        </WorkspaceLink>)}</div>
      </div>
    </section>

    <section className="mk-section" aria-labelledby="mk-responsibility-title">
      <div className="mk-container mk-statement">
        <div><p className="ui-eyebrow ui-eyebrow--brand">Designed with responsibility</p><h2 id="mk-responsibility-title">Built for clarity. <em>Grounded in evidence.</em></h2></div>
        <div><p>Signals are not guarantees. A paper result is a simulated outcome, not a live fill. A connected broker is not an authorized execution destination. These distinctions are part of the product.</p>
          <div className="ui-actions mk-statement-links"><Link className="ui-link" href="/risk">Risk boundaries <Icon name="arrowRight"/></Link><Link className="ui-link" href="/security">Privacy and security <Icon name="arrowRight"/></Link></div></div>
      </div>
    </section>

    <section className="mk-section mk-section--tight" aria-labelledby="mk-cta-title">
      <div className="mk-container">
        <div className="mk-cta">
          <div><h2 id="mk-cta-title">See beyond the signal.</h2><p>Explore entitled signal history, account records, notifications and paper trading. Features depend on your plan and service availability.</p></div>
          <div className="ui-actions"><WorkspaceLink href="/login" className="ui-btn ui-btn--primary ui-btn--lg">Open SignalRankAI <Icon name="arrowRight"/></WorkspaceLink><Link href="/pricing" className="ui-btn ui-btn--lg">Plans and access</Link></div>
        </div>
      </div>
    </section>
    <div className="mk-container"><SiteCredit navigation/></div>
  </main>;
}
