import Link from "next/link";
import { PublicNav } from "../components/PublicNav";
import { SiteCredit } from "../components/SiteCredit";
import { WorkspaceLink } from "../components/WorkspaceLink";

// What a member gets, in plain words. Each item opens the matching part of the workspace.
const offering = [
  { title:"On Telegram", copy:"Each signal arrives as a message with the entry, the stop and three targets, followed by a short note when a target or the stop is hit.", href:"/app/settings", cta:"Link Telegram" },
  { title:"In the web app", copy:"The same signals with a chart, the record of the setup behind each one, and filters for market and timeframe.", href:"/app/signals", cta:"Open signals" },
  { title:"Paper trading", copy:"Try signals on a simulated account before you risk anything. Paper positions and paper results are always labelled as paper.", href:"/app/paper", cta:"Open the paper desk" },
  { title:"Your broker accounts", copy:"Link MT4/MT5, Bybit or Binance to see balances and open positions next to the signals. Linking an account never places a trade on its own.", href:"/app/brokers", cta:"Link an account" },
  { title:"The scoreboard", copy:"Every closed signal, counted: full wins, partial wins, breakevens, losses and the average R. Signals that never triggered are listed separately.", href:"/app/performance", cta:"See performance" },
] as const;

const coverage = [
  ["Crypto", "The most traded coins, quoted against USDT. Stablecoins and pegged tokens are left out."],
  ["Forex", "Majors and the main crosses, scanned during the sessions when they move."],
  ["Stocks", "Large US companies, during US market hours."],
  ["Indices", "US, European and Asian cash indices."],
  ["Commodities", "Gold, silver and crude oil."],
] as const;

// Illustration only: fixed example levels, never fetched or computed, and labelled as an example.
const example = { pair:"ETH/USDT", timeframe:"1h", side:"Long", levels:[
  ["Entry", "2,412.50"], ["Stop", "2,371.80"], ["Target 1", "2,473.55"], ["Target 2", "2,514.30"], ["Target 3", "2,575.30"],
] as const };

export default function Home() {
  return <main className="mk-page">
    <PublicNav/>
    <section className="hm-hero skip-target" id="page-content" tabIndex={-1} aria-labelledby="hm-title">
      <div className="mk-container hm-hero-grid">
        <div className="hm-hero-copy">
          <h1 id="hm-title">Trade setups that come with their track record.</h1>
          <p className="hm-lede">SignalRankAI watches crypto, forex, stocks, indices and commodities around the clock. When a setup appears, we look up how that same kind of setup has done over the past two months. It only reaches you if its record beats what the trade needs to break even.</p>
          <div className="hm-actions">
            <WorkspaceLink href="/login?mode=register" className="ui-btn ui-btn--primary ui-btn--lg">Create a free account</WorkspaceLink>
            <Link href="#how" className="hm-textlink">How we decide what to send</Link>
          </div>
          <p className="hm-small">There is a free plan. Signals are research to help your own decisions, not financial advice.</p>
        </div>

        <figure className="hm-ticket" aria-labelledby="hm-ticket-caption">
          <div className="hm-ticket-head">
            <strong>{example.pair}</strong><span>{example.timeframe} · {example.side}</span>
            <span className="hm-tag">Example</span>
          </div>
          <dl className="hm-ticket-levels">
            {example.levels.map(([label, price])=><div key={label}><dt>{label}</dt><dd>{price}</dd></div>)}
          </dl>
          <p className="hm-ticket-plan">Plan: take half off at target 1 and a quarter at target 2, then move the stop to the entry for the rest.</p>
          <figcaption id="hm-ticket-caption">An example, not a live signal. Real signals also show the setup&rsquo;s record and its break-even rate.</figcaption>
        </figure>
      </div>
    </section>

    <section className="hm-section" id="how" aria-labelledby="hm-how-title">
      <div className="mk-container hm-split">
        <div className="hm-split-head">
          <h2 id="hm-how-title">How a setup gets to you</h2>
          <p className="hm-aside">Most setups don&rsquo;t make it. On a typical day the engine looks at thousands of candidates and sends a handful. Some days it sends none, and that is the system working.</p>
        </div>
        <ol className="hm-steps">
          <li><h3>We scan</h3><p>Every few minutes the engine pulls fresh candles for each market, from 5-minute to daily charts, and runs about a dozen strategies over them: trend, momentum, breakouts and volatility.</p></li>
          <li><h3>We check the record</h3><p>A candidate belongs to a setup, meaning one strategy on one timeframe in one direction. We count how often that setup reached its first target over the last 60 days, take the cautious end of that estimate, and compare it with the hit rate this trade needs to break even under our exit plan. If the record falls short, nothing is sent.</p></li>
          <li><h3>We send it, then keep score</h3><p>A signal that passes goes out with its levels. We follow it until it closes, and the result goes on the scoreboard whether it won or lost.</p></li>
        </ol>
      </div>
    </section>

    <section className="hm-section" aria-labelledby="hm-get-title">
      <div className="mk-container">
        <h2 id="hm-get-title" className="hm-h2">What you get</h2>
        <dl className="hm-offer">
          {offering.map(item=><div key={item.title}>
            <dt>{item.title}</dt>
            <dd><p>{item.copy}</p><WorkspaceLink href={item.href} className="hm-textlink">{item.cta}</WorkspaceLink></dd>
          </div>)}
        </dl>
      </div>
    </section>

    <section className="hm-section" aria-labelledby="hm-cover-title">
      <div className="mk-container hm-split">
        <div className="hm-split-head"><h2 id="hm-cover-title">Markets we cover</h2></div>
        <dl className="hm-cover">
          {coverage.map(([name, copy])=><div key={name}><dt>{name}</dt><dd>{copy}</dd></div>)}
        </dl>
      </div>
    </section>

    <section className="hm-section" aria-labelledby="hm-plain-title">
      <div className="mk-container hm-note">
        <h2 id="hm-plain-title">A few things we won&rsquo;t pretend</h2>
        <p>No signal service wins every trade, and this one doesn&rsquo;t either. We don&rsquo;t promise returns and we don&rsquo;t trade your money for you. When a signal is paper only, the card says so, and some days the right call is no trade at all. If that sounds like the service you want, start on the free plan and judge us by the record.</p>
        <p className="hm-links"><Link className="hm-textlink" href="/risk">Risks of trading</Link><Link className="hm-textlink" href="/methodology">The method in detail</Link><Link className="hm-textlink" href="/security">Privacy and security</Link></p>
      </div>
    </section>

    <section className="hm-section hm-end" aria-labelledby="hm-end-title">
      <div className="mk-container hm-end-inner">
        <h2 id="hm-end-title">Start on the free plan</h2>
        <p>Link Telegram in about a minute. Upgrade only if the record convinces you.</p>
        <div className="hm-actions">
          <WorkspaceLink href="/login?mode=register" className="ui-btn ui-btn--primary ui-btn--lg">Create a free account</WorkspaceLink>
          <Link href="/pricing" className="hm-textlink">Compare plans</Link>
        </div>
      </div>
    </section>
    <div className="mk-container"><SiteCredit navigation/></div>
  </main>;
}
