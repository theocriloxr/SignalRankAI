import Link from "next/link";
import { PublicNav } from "../components/PublicNav";

const markets=["CRYPTO","FX","INDICES","EQUITIES","COMMODITIES"];
const steps=[
  {index:"01",name:"Market data and source",state:"QUALIFY"},
  {index:"02",name:"Strategy and model",state:"EVALUATE"},
  {index:"03",name:"Risk and account policy",state:"ADMIT / REJECT"},
  {index:"04",name:"Entitled delivery",state:"RECEIPT"},
  {index:"05",name:"Lifecycle and outcomes",state:"OBSERVE"},
];
const principles=[
  {number:"01",title:"Freshness before analysis",description:"A stale, unsupported or ambiguous price is a reason to stop. Every asset class needs its own provider and session verification."},
  {number:"02",title:"Evidence over volume",description:"A scan may produce no deliverable signal. Thresholds and rejection reasons matter more than meeting a daily alert quota."},
  {number:"03",title:"No false execution claims",description:"Research signals, simulated fills and broker-confirmed orders carry different evidence. None is silently promoted into another."},
];

export default function Home() {
  return <main className="sr-public-home">
    <div className="sr-public-frame">
      <PublicNav/>
      <section className="sr-public-home-hero" aria-labelledby="sr-home-heading">
        <div className="sr-public-home-hero-top">
          <p className="sr-overline">SignalRankAI — Multi-asset decision intelligence</p>
          <p>RESEARCH / ACCOUNT EVIDENCE / RISK-GATED WORKFLOWS</p>
        </div>
        <h1 id="sr-home-heading">A sharper way to see <em>what qualifies.</em></h1>
        <p className="sr-public-home-lede">Built to examine opportunities across markets, reject uncertain setups, and keep every delivered signal connected to its evidence. Research on the web and Telegram, simulated trading and any certified broker workflow are accountable to the same canonical signal lifecycle.</p>
        <div className="sr-public-home-actions">
          <Link className="button" href="/login">Enter workspace ↗</Link>
          <Link className="button secondary" href="/methodology">Explore the methodology</Link>
        </div>
        <div className="sr-home-markets" aria-label="Market categories">{markets.map(m=><span key={m}>{m}</span>)}</div>
      </section>
      <section className="sr-home-exhibit" aria-label="Illustration of SignalRank qualification principles">
        <div className="sr-home-system">
          <div className="sr-home-system-head"><p className="sr-overline">Decision qualification</p><span>PROCESS / NOT LIVE MARKET DATA</span></div>
          <div className="sr-home-system-steps">{steps.map(step=><div className="sr-home-system-step" key={step.index}>
            <span>{step.index}</span><strong>{step.name}</strong><span>{step.state}</span>
          </div>)}</div>
          <p className="sr-home-system-note">NO TRADE is a legitimate outcome. A high score cannot override missing market, execution or account evidence.</p>
        </div>
        <div className="sr-home-visual" role="img" aria-label="Decorative concentric market-data observation graphic. It displays no prices, results or live status.">
          <div className="sr-home-visual-caption"><span>DATA INTEGRITY / DECISION BOUNDARIES</span><span>CONCEPTUAL VISUALIZATION — NOT A CHART</span></div>
        </div>
      </section>
      <section className="sr-home-chapter" aria-labelledby="sr-principles-heading">
        <div><p className="sr-overline">01 / The decision standard</p><h2 id="sr-principles-heading">Confidence should be traceable.</h2></div>
        <div><p className="sr-home-chapter-intro">Market signals become more useful when you can ask where a quote originated, why a strategy passed, what the model actually measured and whether a result was delivered—or executed.</p>
          <div className="sr-home-principles">{principles.map(principle=><article key={principle.number}>
            <span>{principle.number} / SIGNAL STANDARD</span>
            <h3>{principle.title}</h3><p>{principle.description}</p>
          </article>)}</div>
          <div className="sr-home-chapter-actions"><Link href="/providers">Provider lineage ↗</Link><Link href="/risk">Risk architecture ↗</Link></div>
        </div>
      </section>
      <section className="sr-home-chapter" aria-labelledby="sr-workflows-heading">
        <div><p className="sr-overline">02 / The connected workspace</p><h2 id="sr-workflows-heading">One signal. Distinct outcomes.</h2></div>
        <div className="sr-editorial-sections">
          <article className="sr-editorial-section"><div className="sr-editorial-index"><span>01</span><span>Evidence</span></div>
            <div className="sr-editorial-body"><h3>Delivered signals are not invented positions.</h3><p>Follow an entitled receipt into its model context, delivery proof, lifecycle observations and recorded outcomes. Missing evidence remains visible as unavailable.</p><ul><li>Asset and timeframe scoped details</li><li>Documented strategy and calibrated context</li><li>Receipt provenance and lifecycle history</li></ul></div>
          </article>
          <article className="sr-editorial-section"><div className="sr-editorial-index"><span>02</span><span>Simulation</span></div>
            <div className="sr-editorial-body"><h3>Practice with a separate paper account.</h3><p>Paper balances, positions and results are simulated. They are never mixed with broker equity, real fills or claims of certified performance.</p><ul><li>Account-scoped simulated exposure</li><li>Transparent paper equity and outcomes</li><li>No automatic live brokerage authorization</li></ul></div>
          </article>
          <article className="sr-editorial-section"><div className="sr-editorial-index"><span>03</span><span>Risk policy</span></div>
            <div className="sr-editorial-body"><h3>Broker connections must earn execution eligibility.</h3><p>Account selection, market geometry, free margin, explicit intent and runtime permission remain separate safeguards. A connected provider alone cannot grant an order.</p><ul><li>Per-account authorization and limits</li><li>Explicit rejection of ambiguous destinations</li><li>Provider-confirmed execution evidence</li></ul></div>
          </article>
        </div>
      </section>
      <section className="sr-home-closing" aria-labelledby="sr-home-close">
        <div><p className="sr-overline">Research that can be challenged</p><h2 id="sr-home-close">See the decision. Inspect the evidence.</h2></div>
        <div><p>Open your account workspace to view permitted signal history, paper exposure, market quality, notifications and broker connection records. Features depend on plan access, available services and verification.</p>
          <Link className="button" href="/login">Secure sign-in ↗</Link>
          <Link className="sr-secondary-link" href="/pricing">Plan access and billing details →</Link>
        </div>
      </section>
      <footer className="sr-public-footer">
        <Link href="/">SignalRankAI</Link>
        <span>Information and simulations are not guarantees. Trading involves risk of loss.</span>
        <Link href="/risk">Risk disclosure ↗</Link>
      </footer>
    </div>
  </main>;
}
