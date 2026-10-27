import Link from "next/link";
import { PublicNav } from "../components/PublicNav";
import { SignalLifecycleExperience } from "../components/SignalLifecycleExperience";
import { SiteCredit } from "../components/SiteCredit";
import { WorkspaceLink } from "../components/WorkspaceLink";

const markets=["CRYPTO","FOREX","INDICES","STOCKS","COMMODITIES"];
const pillars=[
  {n:"01",name:"Evidence you can inspect",copy:"Every entitled signal links to its lifecycle, model context and available delivery proof. Missing evidence is never quietly filled in.",href:"/methodology",icon:"◎"},
  {n:"02",name:"Risk that has a voice",copy:"A rejected opportunity is an intentional decision. Risk policies, account boundaries and permissions remain independent of a strategy score.",href:"/risk",icon:"◇"},
  {n:"03",name:"One connected workspace",copy:"Research, signal receipts, simulated trades, journal entries, alerts and broker readiness live alongside their canonical records.",href:"/app",icon:"⌘"},
];
const experiences=[
  {n:"01",label:"SIGNAL INTELLIGENCE",title:"Know why it qualifies.",copy:"Filter delivered decisions by market, strategy and timeframe. Follow the evidence instead of blindly chasing the alert.",href:"/app/signals",cta:"Explore signals"},
  {n:"02",label:"PAPER DESK",title:"Practice, without pretending.",copy:"Keep simulated positions, cash, exposure and P&L distinct from live broker balances or execution claims.",href:"/app/paper",cta:"Explore paper trading"},
  {n:"03",label:"BROKER OVERSIGHT",title:"Connections aren’t permission.",copy:"Review linked-account states and certification boundaries. A broker connection alone cannot approve a trade.",href:"/app/brokers",cta:"Inspect connections"},
];

export default function Home() {
  return <main className="sr-public-home sr-cinema">
    <div className="sr-public-frame">
      <PublicNav/>
      <section className="sr-cinema-hero" aria-labelledby="sr-cinema-title">
        <div className="sr-cinema-hero-copy">
          <p className="sr-cinema-kicker"><span className="sr-cinema-live-mark"/> SIGNALRANKAI / BUILT FOR THE DECISION</p>
          <h1 id="sr-cinema-title">Read the market.<br/><em>Question the signal.</em><br/>Own the decision.</h1>
          <p className="sr-cinema-lede">A multi-asset intelligence ecosystem that connects market research, quality gates, signal evidence and risk-aware account workflows—on the web and through Telegram.</p>
          <div className="sr-cinema-hero-actions"><WorkspaceLink href="/login" className="button">Enter the workspace <span aria-hidden="true">↗</span></WorkspaceLink><Link href="#lifecycle" className="sr-cinema-link">Explore the decision engine <span aria-hidden="true">↓</span></Link></div>
          <div className="sr-cinema-hero-bottom"><span>RESEARCH FIRST</span><span>EVIDENCE BEFORE EXECUTION</span><span>BUILT FOR ACCOUNTABILITY</span></div>
        </div>
        <div className="sr-cinema-hero-art" aria-label="Schematic trading terminal illustration. No market data, balances, or performance figures are shown.">
          <div className="sr-cinema-art-glow" aria-hidden="true"/>
          <div className="sr-cinema-terminal">
            <div className="sr-cinema-terminal-top"><span><i/><i/><i/></span><strong>SR / INTELLIGENCE TERMINAL</strong><small>ILLUSTRATION</small></div>
            <div className="sr-cinema-terminal-layout">
              <div className="sr-cinema-terminal-rail"><span>◎</span><span>▦</span><span>◇</span><span>⊞</span></div>
              <div className="sr-cinema-terminal-canvas">
                <div className="sr-cinema-terminal-label"><span>DECISION EVIDENCE</span><span>SCHEMATIC / NOT LIVE</span></div>
                <div className="sr-cinema-terminal-radar" aria-hidden="true">
                  <div className="sr-cinema-radar-rings"/><div className="sr-cinema-radar-axis"/>
                  <div className="sr-cinema-radar-node sr-radar-node-one"/><div className="sr-cinema-radar-node sr-radar-node-two"/><div className="sr-cinema-radar-node sr-radar-node-three"/>
                  <div className="sr-cinema-radar-center"><span>SR</span><small>QUALIFY</small></div>
                </div>
                <div className="sr-cinema-terminal-micro"><span>DATA QUALITY <b>CHECK</b></span><span>STRATEGY <b>REVIEW</b></span><span>RISK <b>ENFORCE</b></span></div>
              </div>
            </div>
            <div className="sr-cinema-terminal-bottom"><span>UNVERIFIED OPPORTUNITIES CAN BE REJECTED</span><span>NO AUTO-TRADE CLAIM</span></div>
          </div>
          <div className="sr-cinema-art-chip sr-cinema-art-chip-top"><span>◎</span><strong>QUALITY GATES</strong><small>BEFORE DELIVERY</small></div>
          <div className="sr-cinema-art-chip sr-cinema-art-chip-bottom"><span>◇</span><strong>ACCOUNT EVIDENCE</strong><small>TRACEABLE LIFECYCLE</small></div>
        </div>
      </section>
      <div className="sr-cinema-market-bar" aria-label="Supported market categories"><span>ONE INTELLIGENCE LAYER / FIVE MARKET FAMILIES</span><div>{markets.map(m=><span key={m}>{m}</span>)}</div></div>
      <section className="sr-cinema-position" aria-labelledby="sr-cinema-position-title">
        <div className="sr-cinema-position-head"><p className="sr-cinema-kicker">01 / THE SIGNALRANK STANDARD</p><h2 id="sr-cinema-position-title">The best decision<br/>is sometimes <em>no trade.</em></h2></div>
        <div className="sr-cinema-position-copy"><p>More alerts do not mean better intelligence. SignalRankAI is built around evidence, explicit rejection, and the difference between an observed market opportunity and an executed order.</p><Link href="/methodology">Read the methodology <span aria-hidden="true">↗</span></Link></div>
      </section>
      <section className="sr-cinema-pillars" aria-label="Product design principles">{pillars.map(p=><WorkspaceLink href={p.href} className="sr-cinema-pillar" key={p.n}>
        <div className="sr-cinema-pillar-top"><span>{p.n} / 03</span><span>{p.icon}</span></div><div><h3>{p.name}</h3><p>{p.copy}</p></div><div className="sr-cinema-pillar-bottom"><span>EXPLORE THE STANDARD</span><span aria-hidden="true">↗</span></div></WorkspaceLink>)}</section>
    </div>
    <SignalLifecycleExperience/>
    <section className="sr-cinema-product" aria-labelledby="sr-cinema-product-title">
      <div className="sr-public-frame">
        <div className="sr-cinema-product-head"><p className="sr-cinema-kicker">03 / YOUR WORKSPACE, CONNECTED</p><h2 id="sr-cinema-product-title">From the first scan<br/>to the <em>full picture.</em></h2><p>One secure workspace for the signal lifecycle. Data and access always come from your authenticated account, not this illustration.</p></div>
        <div className="sr-cinema-product-grid">{experiences.map(item=><article key={item.n} className="sr-cinema-product-card">
          <div className="sr-cinema-product-card-top"><span>{item.n} / 03</span><span>↗</span></div><div><p>{item.label}</p><h3>{item.title}</h3><span>{item.copy}</span></div><WorkspaceLink href={item.href}>{item.cta} <span aria-hidden="true">↗</span></WorkspaceLink></article>)}</div>
      </div>
    </section>
    <section className="sr-cinema-statement"><div className="sr-public-frame"><p className="sr-cinema-kicker">04 / DESIGNED WITH RESPONSIBILITY</p><h2>Built for clarity.<br/><em>Grounded in evidence.</em></h2><p>Signals are not guarantees. A paper result is not a live fill. A connected broker is not an authorized execution destination. The distinction is part of the product.</p><div><Link href="/risk">Explore risk boundaries ↗</Link><Link href="/security">Privacy and security ↗</Link></div></div></section>
    <section className="sr-public-frame sr-cinema-outro" aria-labelledby="sr-cinema-outro-title"><div><p className="sr-cinema-kicker">THE NEXT DECISION IS YOURS</p><h2 id="sr-cinema-outro-title">See beyond<br/><em>the signal.</em></h2></div><div><p>Explore real entitled signal history, account records, notifications and trading simulations. Features remain dependent on account access and service availability.</p><WorkspaceLink href="/login" className="button">Open SignalRankAI <span aria-hidden="true">↗</span></WorkspaceLink><Link href="/pricing">Explore plans and access ↗</Link></div></section>
    <div className="sr-public-frame"><SiteCredit navigation/></div>
  </main>;
}
