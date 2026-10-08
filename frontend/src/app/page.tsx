import Link from "next/link";
import { PublicNav } from "../components/PublicNav";

const markets = ["Crypto", "FX", "Indices", "Equities", "Commodities"];
const principles = [
  ["Fresh data first", "Signals are blocked when market data is stale, ambiguous, or outside the certified provider path."],
  ["Evidence over frequency", "SignalRankAI can return NO TRADE. It does not weaken quality gates just to fill a feed."],
  ["Traceable decisions", "Qualified signals carry strategy, model, data-lineage, freshness, risk, and lifecycle evidence."],
];

export default function Home() {
  return (
    <main>
      <section className="hero">
        <PublicNav />
        <div className="heroGrid">
          <div>
            <p className="eyebrow">Multi-asset decision intelligence</p>
            <h1>High-conviction trading research with a visible evidence trail.</h1>
            <p className="lede">SignalRankAI scans multiple markets, rejects weak or stale setups, and turns qualified opportunities into explainable signals for web, Telegram, paper trading, and certified broker workflows.</p>
            <div className="actions"><Link className="button" href="/app">Launch workspace</Link><Link className="button secondary" href="/methodology">See how signals qualify</Link></div>
            <div className="marketRow">{markets.map((m)=><span key={m}>{m}</span>)}</div>
          </div>
          <div className="terminalCard">
            <div className="terminalHead"><span>QUALIFICATION PIPELINE</span><span className="liveDot">METHOD</span></div>
            <div className="metric"><span>Universe</span><strong>Multi-asset</strong></div><div className="metric"><span>Data gate</span><strong>Fresh + certified</strong></div><div className="metric"><span>Strategy</span><strong>Consensus</strong></div><div className="metric"><span>ML</span><strong>Champion-gated</strong></div><div className="metric"><span>Risk</span><strong>Fail-closed</strong></div>
            <div className="decision">NO QUALIFIED SETUP IS A VALID OUTPUT</div>
          </div>
        </div>
      </section>
      <section className="section"><p className="eyebrow">Operating principles</p><div className="cards">{principles.map(([title,body])=><article className="card" key={title}><h2>{title}</h2><p>{body}</p></article>)}</div></section>
      <section className="section split"><div><p className="eyebrow">One canonical signal truth</p><h2>Research, delivery, paper trading, and execution all refer to the same lifecycle.</h2></div><p className="muted">Web and Telegram are delivery channels, not separate signal engines. Paper and broker workflows remain separately identified so historical, simulated, and executed outcomes are never blended into one misleading performance number.</p></section>
      <footer><span>SignalRankAI</span><span>Trading involves risk. Signals are decision support, not guaranteed outcomes.</span></footer>
    </main>
  );
}
