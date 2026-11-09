"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import client from "../lib/client";
import { AccountCreation } from "./AccountCreation";
import { SignalChart } from "./SignalChart";
import { SetupRecords } from "./SetupRecords";
import { SignalEvidence } from "./SignalEvidence";
import { SignalFeedback } from "./SignalFeedback";
import { SetupEvidence, SetupLine, PaperOnlyTag, isPaperOnly } from "./SignalSetup";
import { NotificationCenter } from "./NotificationCenter";
import { NotificationPreferences } from "./NotificationPreferences";
import { DeviceNotifications } from "./DeviceNotifications";
import { WatchlistsView } from "./WatchlistsView";
import { JournalView } from "./JournalView";
import { TradingPreferences } from "./TradingPreferences";
import { SupportCenter } from "./SupportCenter";
import { AlertRules } from "./AlertRules";
import { PaperDesk } from "./PaperDesk";
import { PaperEquityChart } from "./PaperEquityChart";
import { BrokerAccounts } from "./BrokerAccounts";
import { MarketDirectory } from "./MarketDirectory";
import { AccountSecurity } from "./AccountSecurity";
import { DemoBrokerConnection } from "./DemoBrokerConnection";
import { BillingCenter } from "./BillingCenter";
import { DeveloperAccess } from "./DeveloperAccess";
import { PlanAndReferrals } from "./PlanAndReferrals";
import { PrivacyCenter } from "./PrivacyCenter";
import { OwnerControls } from "./OwnerControls";
import { SignalFilters, type SignalQuery } from "./SignalFilters";
import { Icon } from "./ui/Icon";
import { Badge, Card, DirectionBadge, Empty, KV, KVList, Notice, Skeleton, Stat, TableWrap, type Tone } from "./ui/primitives";
import {
  display, finite, moneyLabel, numberLabel, priceLabel,
  probabilityLabel, record, riskReward, rows, statusText, targetPrices, timeLabel,
  type Row,
} from "../lib/presentation";

type Section =
  | "overview" | "signals" | "markets" | "research" | "watchlists" | "alerts" | "notifications"
  | "paper" | "portfolio" | "performance" | "journal" | "brokers"
  | "billing" | "support" | "settings" | "operations";

type Outcome = { data: Row | null; status: number; success: boolean };
type State = { kind: "loading" | "ready" | "error" | "auth"; data: Row | null; status?: number };
const titles: Record<Section, string> = {
  overview: "Overview", signals: "Signals", markets: "Markets",
  research: "Strategies", watchlists: "Watchlists", alerts: "Alerts", notifications: "Notifications", paper: "Paper desk",
  portfolio: "Portfolio", performance: "Performance", journal: "Journal",
  brokers: "Brokers", billing: "Plan and billing", support: "Support",
  settings: "Settings", operations: "Operations",
};
const descriptions: Record<Section, string> = {
  overview: "Where your account stands and what came in recently.",
  signals: "Every signal sent to you, newest first. Open one to see its setup record and how it played out.",
  markets: "Look up an instrument, and see how many candidates the filters turned away and why.",
  research: "How many signals each strategy produced recently. Busy isn't the same as good: outcomes are on the Performance page.",
  watchlists: "Instruments you want to keep an eye on.",
  alerts: "Rules that tell you when a price, a signal or a data provider does something.",
  notifications: "Messages we've sent you, and where you'd like to get them.",
  paper: "Practise with pretend money. Orders here stay on the paper account and never reach a broker.",
  portfolio: "What your paper account holds right now, grouped by instrument.",
  performance: "How the signals sent to you turned out, counted the same way the Telegram bot counts them.",
  journal: "Your own notes on signals and trades.",
  brokers: "Accounts you've linked, what they're allowed to do and their records.",
  billing: "Your plan, renewals and receipts.",
  support: "Your conversations with our team.",
  settings: "Signal preferences, sign-in and security, plan, API access and privacy.",
  operations: "Owner tools: what's deployed, the safety switches, account merges and AI spend.",
};

export const workspaceTitles = titles;

/* Every request passes through the typed, cookie-authenticated canonical client.
   No workspace response is cached in browser storage and no broker order is issued. */
async function readSection(section: Section, signalId?: string, filters: SignalQuery = {}, offset = 0): Promise<Outcome> {
  const outcome = (() => {
    switch (section) {
      case "overview": return client.GET("/api/v1/platform/dashboard");
      case "signals": return signalId
        ? client.GET("/api/v1/platform/signals/{signal_id}", { params: { path: { signal_id: signalId } } })
        : client.GET("/api/v1/platform/signals", { params: { query: { limit: 30, offset, ...filters } } });
      case "markets": return client.GET("/api/v1/platform/quality");
      case "research": return client.GET("/api/v1/platform/strategy-leaderboard");
      case "watchlists": return client.GET("/api/v1/platform/watchlists");
      case "alerts": return client.GET("/api/v1/platform/alerts");
      case "notifications": return client.GET("/api/v1/platform/notifications");
      case "paper": return client.GET("/api/v1/platform/paper");
      case "portfolio": return client.GET("/api/v1/platform/portfolio");
      case "performance": return client.GET("/api/v1/platform/performance");
      case "journal": return client.GET("/api/v1/platform/journal");
      case "brokers": return client.GET("/api/v1/platform/broker/connections");
      case "billing": return client.GET("/api/v1/platform/billing");
      case "support": return client.GET("/api/v1/platform/support/tickets");
      case "settings": return client.GET("/api/v1/platform/trading-profile");
      case "operations": return client.GET("/api/v1/platform/operator/overview");
    }
  })();
  try {
    const response = await outcome;
    return { data: response.data ? record(response.data) : null, status: response.response.status, success: Boolean(response.data) && response.response.ok };
  } catch {
    return { data: null, status: 0, success: false };
  }
}

/** Plain words for stored outcome codes; anything unrecognised is shown as stored. */
const outcomeWords: Record<string, [string, Tone]> = {
  tp3: ["Target 3 hit", "positive"], tp: ["Target hit", "positive"], win: ["Won", "positive"],
  tp2: ["Target 2 hit", "positive"], tp1: ["Target 1 hit", "positive"],
  stopped_at_tp1: ["Stopped after target 1", "positive"], stopped_at_tp2: ["Stopped after target 2", "positive"],
  partial_tp: ["Partly taken", "positive"], partial_win_be: ["Partly taken", "positive"],
  sl: ["Stopped out", "negative"], loss: ["Stopped out", "negative"],
  breakeven: ["Breakeven", "neutral"], time_stop: ["Closed on time", "neutral"],
  active: ["Open", "info"], open: ["Open", "info"], pending: ["Waiting for entry", "info"], pending_entry: ["Waiting for entry", "info"],
  missed_entry: ["Entry never reached", "neutral"], expired: ["Expired", "neutral"], not_triggered: ["Entry never reached", "neutral"],
};

function outcomeOf(value: unknown): [string, Tone] {
  const code = display(value, "").toLowerCase();
  if (!code) return ["No result yet", "neutral"];
  return outcomeWords[code] ?? [code.replace(/_/g, " ").replace(/^./, c => c.toUpperCase()), "neutral"];
}

const statusTones: Record<string, Tone> = { info: "info", positive: "positive", negative: "negative", neutral: "neutral" };

/** Where the trade stands: the server's lifecycle-first status, else the stored outcome. */
function statusOf(signal: Row): [string, Tone] {
  const status = record(signal.trade_status);
  const label = display(status.label, "");
  if (label) return [label, statusTones[display(status.tone, "neutral")] ?? "neutral"];
  return outcomeOf(signal.outcome_status);
}

/** What the trade has made, in R, per $100 risked and as a price move. */
function TradeResult({ signal }: { signal: Row }) {
  const status = record(signal.trade_status);
  const realized = finite(status.realized_r);
  const banked = finite(status.banked_r);
  const per100 = finite(status.result_per_100_risk);
  const move = finite(status.realized_pct);
  const openShare = finite(status.open_share);
  const signed = (value: number, digits = 2) => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(digits)}`;
  if (realized !== null) {
    return <p className="ws-signal-meta"><span>Result <b>{signed(realized)}R</b></span>
      {per100 !== null && <span><b>{signed(per100)}</b> per $100 risked</span>}
      {move !== null && <span>Price move <b>{signed(move)}%</b></span>}</p>;
  }
  if (banked !== null) {
    return <p className="ws-signal-meta"><span>Banked so far <b>{signed(banked)}R</b></span>
      {per100 !== null && <span><b>{signed(per100)}</b> per $100 risked</span>}
      {openShare !== null && openShare > 0 && <span><b>{Math.round(openShare * 100)}%</b> still open, stop at entry</span>}</p>;
  }
  if (status.closed === true && status.entry_triggered === false) {
    return <p className="ws-signal-meta"><span>No position was opened, so no profit or loss.</span></p>;
  }
  return null;
}

// Live "Now" price on open signal cards (owner report, 9 Nov 2026: "it doesn't
// show current prices on the site"). Cards on the same asset share one quote.
const quoteCache = new Map<string, { at: number; value: Promise<number | null> }>();
function liveQuote(asset: string): Promise<number | null> {
  const hit = quoteCache.get(asset);
  if (hit && Date.now() - hit.at < 15000) return hit.value;
  const value = client.GET("/api/v1/platform/live-price", { params: { query: { asset } } })
    .then(r => (r.response.ok ? finite(record(r.data).price) : null))
    .catch(() => null);
  quoteCache.set(asset, { at: Date.now(), value });
  return value;
}

function LiveNow({ signal }: { signal: Row }) {
  const asset = display(signal.asset, "");
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!asset) return;
    let off = false;
    const tick = async () => { const price = await liveQuote(asset); if (!off) setNow(price); };
    void tick();
    const timer = window.setInterval(() => { void tick(); }, 20000);
    return () => { off = true; window.clearInterval(timer); };
  }, [asset]);
  const entry = finite(signal.entry), stop = finite(signal.stop_loss);
  if (now === null) return null;
  const short = display(signal.direction, "").toLowerCase().startsWith("s");
  const risk = entry !== null && stop !== null ? Math.abs(entry - stop) : 0;
  const moved = risk > 0 && entry !== null ? ((short ? entry - now : now - entry) / risk) : null;
  return <div className="ws-level ws-level--now"><dt>Now</dt>
    <dd>{priceLabel(now)}{moved !== null && <small className={moved >= 0 ? "ws-up" : "ws-down"}> {moved >= 0 ? "+" : ""}{numberLabel(moved)}R</small>}</dd></div>;
}

function SignalRecord({ signal, detail = false }: { signal: Row; detail?: boolean }) {
  const id = display(signal.signal_id, "");
  const direction = display(signal.direction, "");
  const probability = finite(signal.ml_probability_calibrated);
  const [outcome, tone] = statusOf(signal);
  const targets = targetPrices(signal.take_profit);
  const rr = riskReward(signal.entry, signal.stop_loss, targets, signal.rr_estimate ?? signal.rr_final);
  const locked = signal.exact_levels_locked === true;
  const level = (value: unknown) => locked && finite(value) === null ? "Paid plans" : priceLabel(value);
  const Heading = detail ? "h2" : "h3";
  return <article className="ws-signal" data-paper={isPaperOnly(signal) ? "true" : undefined}>
    <header className="ws-signal-head">
      <div>
        <Heading className="ws-signal-symbol">{display(signal.asset, "Instrument hidden")}</Heading>
        <p className="ws-signal-sub"><DirectionBadge direction={direction}/> · {display(signal.timeframe, "no timeframe")} · {display(signal.asset_class, "market")}</p>
      </div>
      <div className="ws-signal-tags">{isPaperOnly(signal) && <PaperOnlyTag/>}<Badge tone={tone} plain>{outcome}</Badge></div>
    </header>
    <dl className="ws-levels">
      {record(signal.trade_status).closed !== true && !locked && <LiveNow signal={signal}/>}
      <div className="ws-level"><dt>Entry</dt><dd>{level(signal.entry)}</dd></div>
      <div className="ws-level ws-level--stop"><dt>Stop</dt><dd>{level(signal.stop_loss)}</dd></div>
      {targets.length ? targets.map((price, i) => <div className="ws-level ws-level--target" key={i}>
        <dt>Target {i + 1}</dt><dd>{priceLabel(price)}</dd></div>)
        : <div className="ws-level ws-level--target"><dt>Target</dt><dd>Not set</dd></div>}
    </dl>
    <TradeResult signal={signal}/>
    {!detail && <SetupLine signal={signal}/>}
    <p className="ws-signal-meta">
      <span>Reward to risk <b>{rr === null ? "not set" : `1 : ${numberLabel(rr)}`}</b></span>
      <span>{display(signal.strategy_name, "Strategy not recorded")}</span>
      {probability !== null && probability >= 0 && probability <= 1 && <span>Model <b>{probabilityLabel(probability)}</b></span>}
    </p>
    <footer className="ws-signal-foot"><span>Sent {timeLabel(signal.delivered_at)}</span>
      {!detail && id && <Link className="ui-link" href={`/app/signals/${encodeURIComponent(id)}`}>Open signal <Icon name="arrowRight"/></Link>}</footer>
  </article>;
}

function SignalView({ data, detail = false, offset = 0, onPage }: { data: Row; detail?: boolean; offset?: number; onPage?: (offset: number)=>void }) {
  if (detail) {
    const candidate = record(data.signal);
    return <div className="ws-stack">
      <Link className="ui-link" href="/app/signals"><Icon name="arrowLeft"/> All signals</Link>
      {Object.keys(candidate).length ? <>
        <div className="ws-detail-top"><SignalRecord signal={candidate} detail /><SetupEvidence source={data.setup_record ?? candidate.segment_evidence}/></div>
        {isPaperOnly(candidate) && <p className="ws-aside"><PaperOnlyTag/> The model scored this one below its usual bar, so it&rsquo;s for paper trading only. Try it on the paper desk first.</p>}
        <SignalChart data={data} /><SignalEvidence data={data} /><SignalFeedback signalId={display(candidate.signal_id, "")} />
        <p className="ws-aside">A signal is an idea with levels, not an order. Nothing is placed with a broker unless you place it.</p>
      </> : <Empty title="We couldn't find this signal on your account.">It may belong to another account or plan.</Empty>}
    </div>;
  }
  const items = rows(data.signals);
  const paper = items.filter(isPaperOnly).length;
  return <div className="ws-stack">
    {paper > 0 && <p className="ws-aside"><PaperOnlyTag/> {paper === 1 ? "One signal on this page is" : `${paper} signals on this page are`} for practice on the paper desk only, because the model scored {paper === 1 ? "it" : "them"} below its usual bar.</p>}
    {items.length ? <div className="ws-cards">{items.map((s, i) => <SignalRecord key={display(s.signal_id, String(i))} signal={s}/>)}</div>
      : <Empty title="No signals here yet.">We only send a signal when a setup&rsquo;s record beats what the trade needs to break even, so quiet days happen. Try clearing the filters.</Empty>}
    {onPage&&<nav className="ui-pagination" aria-label="Signal history pages">
      <span>Page {Math.floor(offset/30)+1}, {items.length} signals (total count not reported)</span>
      <div className="ui-actions">
        <button className="ui-btn ui-btn--sm" type="button" disabled={offset===0} onClick={()=>onPage(Math.max(0,offset-30))}><Icon name="arrowLeft"/>Newer</button>
        <button className="ui-btn ui-btn--sm" type="button" disabled={items.length<30} onClick={()=>onPage(offset+30)}>Older<Icon name="arrowRight"/></button>
      </div>
    </nav>}
  </div>;
}

const quickLinks: { href: string; label: string; copy: string }[] = [
  { href:"/app/signals", label:"Signals", copy:"What was sent, with each setup's record" },
  { href:"/app/performance", label:"Performance", copy:"How those signals turned out" },
  { href:"/app/paper", label:"Paper desk", copy:"Try signals with pretend money" },
  { href:"/app/markets", label:"Markets", copy:"Instruments and what the filters turned away" },
  { href:"/app/alerts", label:"Alerts", copy:"Price and signal rules" },
  { href:"/app/brokers", label:"Brokers", copy:"Linked accounts and their limits" },
];

function OverviewView({ data }: { data: Row }) {
  const summary = record(data.summary), user = record(data.user), subscription = record(data.subscription);
  const name = display(user.display_name, "");
  const tier = display(subscription.tier, display(user.tier, "unknown"));
  return <div className="ws-stack">
    <section className="ws-hero-card" aria-labelledby="ws-welcome">
      <h2 id="ws-welcome">{name ? `Welcome back, ${name}.` : "Welcome back."}</h2>
      <p>You&rsquo;re on the <b>{tier}</b> plan{subscription.status === "active" ? "" : subscription.status ? ` (${display(subscription.status)})` : ""}.
        Signals only arrive when a setup has earned it, so some days are quiet.</p>
      <div className="ui-actions"><Link className="ui-btn ui-btn--primary" href="/app/signals">See your signals</Link><Link className="hm-textlink" href="/app/settings">Settings</Link></div>
    </section>
    <div className="ui-stat-grid">
      <Stat label="Signals received" value={numberLabel(summary.delivered_signals, 0)} />
      <Stat label="Open paper positions" value={numberLabel(summary.open_positions, 0)} />
      <Stat label="Paper cash" value={numberLabel(summary.paper_cash)} detail="Pretend money" />
      <Stat label="Watchlists" value={numberLabel(summary.watchlists, 0)} />
    </div>
    <nav className="ws-quick-links" aria-label="Go to">{quickLinks.map(link=><Link key={link.href} href={link.href} className="ws-quick-link">
      <span>{link.label}</span><small>{link.copy}</small></Link>)}</nav>
    <div className="ws-grid-2">
      <Card title="Your plan">
        <KVList><KV label="Plan" value={tier}/><KV label="Subscription" value={display(subscription.status, "Not confirmed")}/><KV label="Account" value={display(user.account_status)}/></KVList>
        <Link className="ui-link" href="/app/billing">Plan and billing <Icon name="arrowRight"/></Link>
      </Card>
      <Card title="Broker accounts">
        <p className="ui-card-desc">Linking a broker lets you see its balance and limits here. It doesn&rsquo;t let us trade for you.</p>
        <Link className="ui-link" href="/app/brokers">Brokers <Icon name="arrowRight"/></Link>
      </Card>
    </div>
  </div>;
}

function PaperView({ data }: { data: Row }) {
  const account = record(data.account), snapshot = record(data.snapshot), positions = rows(data.positions);
  const currency = account.currency;
  // Open and closed trades are separate tables. Until 8 Nov 2026 every
  // position, closed ones included, sat under "Open positions" with its
  // *open* profit (USD 0.00 once closed), so closed results were never shown.
  const open = positions.filter(p => display(p.status, "").toLowerCase() === "open");
  const closed = positions.filter(p => display(p.status, "").toLowerCase() !== "open");
  const start = finite(snapshot.starting_balance ?? account.starting_balance);
  const equity = finite(snapshot.equity);
  const realized = finite(snapshot.realized_pnl);
  const unrealized = finite(snapshot.unrealized_pnl);
  const growth = start !== null && start > 0 && equity !== null ? ((equity - start) / start) * 100 : null;
  const wins = closed.filter(p => (finite(p.realized_pnl) ?? 0) > 0).length;
  const openFees = open.reduce((sum, p) => sum + (finite(p.entry_fee) ?? 0), 0);
  const signed = (value: number | null) => value === null ? "—" : moneyLabel(value, currency);
  const pct = (value: number | null) => value === null ? "—" : `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(2)}%`;
  return <div className="ws-stack">
    <div className="ui-stat-grid">
      <Stat label="Starting balance" value={moneyLabel(start, currency)} />
      <Stat label="Equity now" value={moneyLabel(equity, currency)} />
      <Stat label="Return" value={pct(growth)} />
      <Stat label="Cash not in positions" value={moneyLabel(account.cash_balance ?? snapshot.cash_balance, currency)} />
      <Stat label="Realised profit or loss" value={signed(realized)} />
      <Stat label="Open profit or loss" value={signed(unrealized)} />
      <Stat label="Open positions" value={numberLabel(open.length, 0)} />
      <Stat label="Closed trades won" value={closed.length ? `${wins} of ${closed.length}` : "—"} />
    </div>
    {start !== null && equity !== null && <p className="ws-aside">
      Equity = starting balance {moneyLabel(start, currency)} + realised {signed(realized)} + open {signed(unrealized)}
      {openFees > 0 ? <> − entry fees on open positions {moneyLabel(openFees, currency)}</> : null}. Cash is equity minus the value held in open positions.
    </p>}
    <Card title="Open positions">{open.length ? <TableWrap label="Open paper positions"><thead><tr><th>Instrument</th><th>Side</th><th>Entry</th><th>Now</th><th>Stop</th><th>Target</th><th>Size</th><th>Value</th><th>Open profit or loss</th><th>Opened</th></tr></thead><tbody>{open.map((p,i)=><tr key={display(p.position_id,String(i))}><th>{display(p.asset)}</th><td><DirectionBadge direction={display(p.direction,"")}/></td><td>{numberLabel(p.fill_entry,6)}</td><td>{numberLabel(p.current_price,6)}</td><td>{numberLabel(p.stop_loss,6)}</td><td>{numberLabel(p.target_price,6)}</td><td>{numberLabel(p.quantity,6)}</td><td>{moneyLabel(p.notional,currency)}</td><td>{moneyLabel(p.unrealized_pnl,currency)}</td><td>{timeLabel(p.opened_at)}</td></tr>)}</tbody></TableWrap>:<Empty title="Nothing open on the paper desk.">Signals you follow on paper show up here.</Empty>}</Card>
    <Card title="Closed trades">{closed.length ? <TableWrap label="Closed paper trades"><thead><tr><th>Instrument</th><th>Side</th><th>Entry</th><th>Exit</th><th>Size</th><th>Result</th><th>R</th><th>Fees</th><th>Closed by</th><th>Closed</th></tr></thead><tbody>{closed.map((p,i)=>{const pnl=finite(p.realized_pnl), r=finite(p.r_multiple), fees=(finite(p.entry_fee)??0)+(finite(p.exit_fee)??0);
      return <tr key={display(p.position_id,String(i))}><th>{display(p.asset)}</th><td><DirectionBadge direction={display(p.direction,"")}/></td><td>{numberLabel(p.fill_entry,6)}</td><td>{numberLabel(p.exit_price,6)}</td><td>{numberLabel(p.quantity,6)}</td><td><Badge tone={pnl===null?"neutral":pnl>0?"positive":pnl<0?"negative":"neutral"} plain>{moneyLabel(pnl,currency)}</Badge></td><td>{r===null?"—":`${r>=0?"+":"−"}${Math.abs(r).toFixed(2)}R`}</td><td>{moneyLabel(fees,currency)}</td><td>{display(p.exit_reason,"—")}</td><td>{timeLabel(p.closed_at)}</td></tr>;})}</tbody></TableWrap>:<Empty title="No closed paper trades yet.">Finished trades and their results appear here.</Empty>}</Card>
  </div>;
}

function PortfolioView({ data }: { data: Row }) {
  const account = record(data.account), exposures = rows(data.exposures);
  return <div className="ws-stack">
    <p className="ws-aside">This is your paper account only. Balances at linked brokers are on the Brokers page.</p>
    <div className="ui-stat-grid"><Stat label="Paper equity" value={moneyLabel(data.equity,account.currency)}/><Stat label="Instruments held" value={numberLabel(exposures.length,0)}/></div>
    <Card title="By instrument">{exposures.length?<TableWrap label="Exposure by instrument"><thead><tr><th>Instrument</th><th>Class</th><th>Side</th><th>Positions</th><th>Size</th><th>Open profit or loss</th></tr></thead><tbody>{exposures.map((p,i)=><tr key={display(p.asset,String(i))+"-"+i}><th>{display(p.asset)}</th><td>{display(p.asset_class)}</td><td><DirectionBadge direction={display(p.direction,"")}/></td><td>{numberLabel(p.positions,0)}</td><td>{moneyLabel(p.notional,account.currency)}</td><td>{moneyLabel(p.unrealized_pnl,account.currency)}</td></tr>)}</tbody></TableWrap>:<Empty title="Nothing held right now.">Open paper positions appear here, grouped by instrument.</Empty>}</Card>
    <PaperEquityChart ledger={rows(data.equity_curve)} currency={account.currency}/>
  </div>;
}

/** Minimum evaluated outcomes before a ratio is shown without a small-sample warning. */
const MIN_SAMPLE = 30;

function PerformanceView({ data }: { data: Row }) {
  const summary = record(data.summary), breakdown=rows(data.breakdown);
  const sample = finite(summary.signals);
  const parts: [string, unknown, string][] = [
    ["Reached target 3", summary.wins, "positive"], ["Took partial profit", summary.partial_wins, "partial"],
    ["Breakeven or closed on time", summary.breakeven, "neutral"], ["Stopped out", summary.losses, "negative"],
  ];
  const shown = sample !== null && sample > 0;
  const waiting = finite(summary.open) === null || finite(summary.not_triggered) === null ? null : (finite(summary.open) ?? 0) + (finite(summary.not_triggered) ?? 0);
  return <div className="ws-stack">
    <section className="ui-card" aria-labelledby="ws-score-title">
      <header className="ui-card-head"><div>
        <h2 className="ui-card-title" id="ws-score-title">{shown ? `${numberLabel(sample,0)} closed signals` : "No closed signals yet"}</h2>
        <p className="ui-card-desc">Out of {numberLabel(summary.delivered,0)} sent to you. {waiting === 1 ? "1 is still open or never reached its entry, and isn't counted." : `${numberLabel(waiting,0)} are still open or never reached their entry, and aren't counted.`}</p>
      </div></header>
      {shown && <>
        <div className="ws-outcome-bar" role="img" aria-label={parts.map(([label, value]) => `${label}: ${numberLabel(value,0)}`).join(", ")}>
          {parts.map(([label, value, kind]) => { const n = finite(value) ?? 0; return n > 0 ? <span key={label} data-kind={kind} style={{flexGrow:n}}/> : null; })}
        </div>
        <dl className="ws-outcome-key">{parts.map(([label, value, kind]) => <div key={label} data-kind={kind}><dt>{label}</dt><dd>{numberLabel(value,0)}</dd></div>)}</dl>
      </>}
      {sample !== null && sample < MIN_SAMPLE && <p className="ws-aside">{shown ? `That's only ${numberLabel(sample,0)}.` : ""} Below {MIN_SAMPLE} closed signals, the rates below can swing a long way on one trade. Read them as a rough early picture.</p>}
    </section>
    <div className="ui-stat-grid">
      <Stat label="Full-win rate" value={probabilityLabel(summary.win_rate)} detail="Target 3 hits against stop-outs, ignoring partials and breakevens"/>
      <Stat label="Closed in profit" value={probabilityLabel(summary.profitable_rate)} detail="Any close above zero, partials included"/>
      <Stat label="Average result" value={finite(summary.average_r) === null ? "Unavailable" : `${numberLabel(summary.average_r)} R`} detail="Per closed signal, where 1 R is the planned risk"/>
      <Stat label="Total" value={finite(summary.total_r) === null ? "Unavailable" : `${numberLabel(summary.total_r)} R`} detail="All closed signals added up"/>
    </div>
    <Card title="By instrument" description="Closed signals only. R is the result divided by the planned risk, so a full stop-out is −1 R.">{breakdown.length?<TableWrap label="Performance by instrument"><thead><tr><th>Instrument</th><th>Timeframe</th><th>Closed</th><th>Target 3</th><th>Stopped</th><th>Average R</th><th>Total R</th></tr></thead><tbody>{breakdown.map((p,i)=>{
      const n = finite(p.signals);
      return <tr key={display(p.asset,String(i))+"-"+i}><th>{display(p.asset)}</th><td>{display(p.timeframe)}</td><td>{numberLabel(p.signals,0)}{n !== null && n < 10 && <span className="ws-few"> (small sample)</span>}</td><td>{numberLabel(p.wins,0)}</td><td>{numberLabel(p.losses,0)}</td><td>{numberLabel(p.average_r)}</td><td>{numberLabel(p.total_r)}</td></tr>;})}</tbody></TableWrap>:<Empty title="Nothing has closed yet.">Rows appear here once signals reach a target, their stop or their time limit.</Empty>}</Card>
    <p className="ws-aside">{display(summary.disclaimer,"Past results don't promise future ones.")} These figures {summary.claim_certified === true ? "have" : "haven't"} been checked by an outside auditor.</p>
    <SetupRecords/>
  </div>;
}

function QualityView({ data }: { data: Row }) {
  const bucket=record(data.reject_buckets),reasons=rows(data.top_reasons);
  const categories=Object.entries(bucket).filter(([key])=>["ml","score","news","stale","slippage","other"].includes(key));
  const words: Record<string,string> = { ml:"Model score", score:"Quality score", news:"News window", stale:"Stale data", slippage:"Slippage", other:"Other" };
  return <Card title="What the filters did" eyebrow={`Last ${numberLabel(data.window_hours,0)} hours`} description="Candidates the engine looked at, and how many it turned away. This is a count of decisions, not a forecast of how many signals you'll get.">
    <div className="ui-stat-grid"><Stat label="Sent" value={numberLabel(data.issued,0)}/><Stat label="Turned away" value={numberLabel(data.rejected_or_skipped,0)}/><Stat label="Share sent" value={probabilityLabel(data.acceptance_rate)}/></div>
    {finite(data.issued)===0&&finite(data.rejected_or_skipped)===0&&<Notice tone="warning">No decisions were recorded in this window. The engine logs rejections even when it sends nothing, so this usually means it wasn&rsquo;t running rather than that markets were quiet.</Notice>}
    <div className="ws-grid-2">
      <div className="ws-subsection"><h3>Why candidates were turned away</h3>{categories.length?<KVList>{categories.map(([key,value])=><KV key={key} label={words[key] ?? key} value={numberLabel(value,0)}/>)}</KVList>:<p className="ui-muted">Nothing reported.</p>}</div>
      <div className="ws-subsection"><h3>Most common reasons</h3>{reasons.length?<KVList>{reasons.map((r,i)=><KV key={display(r.reason,String(i))} label={display(r.reason)} value={numberLabel(r.rows,0)}/>)}</KVList>:<p className="ui-muted">Nothing reported.</p>}</div>
    </div>
    <QualityBreakdowns breakdowns={record(data.breakdowns)}/>
  </Card>;
}

const QUALITY_DIMENSIONS: [string,string][] = [["strategy","Strategy"],["asset","Instrument"],["timeframe","Timeframe"],["layer","Pipeline layer"]];

/** Where decisions are rejected; rows without a recorded strategy stay "(unattributed)". */
function QualityBreakdowns({ breakdowns }: { breakdowns: Row }) {
  const sections=QUALITY_DIMENSIONS.map(([key,label])=>[key,label,rows(breakdowns[key])] as const).filter(([,,items])=>items.length);
  if(!sections.length) return null;
  return <div className="ws-grid-2">{sections.map(([key,label,items])=><div className="ws-subsection" key={key}><h3>By {label.toLowerCase()}</h3><TableWrap label={`Decisions by ${label.toLowerCase()}`}><thead><tr><th>{label}</th><th>Sent</th><th>Turned away</th><th>Share sent</th></tr></thead><tbody>{items.map((item,i)=><tr key={display(item.value,String(i))+"-"+i}><th>{display(item.value)}</th><td>{numberLabel(item.issued,0)}</td><td>{numberLabel(item.rejected_or_skipped,0)}</td><td>{probabilityLabel(item.acceptance_rate)}</td></tr>)}</tbody></TableWrap></div>)}</div>;
}

function ResearchView({ data }: { data: Row }) {
  const items=rows(data.strategies);
  const top=Math.max(1,...items.map(item=>finite(item.signals)??0));
  return <div className="ws-stack">
    <Card title="Signals per strategy" eyebrow={`Last ${numberLabel(data.window_days,0)} days`} description="A count of signals each strategy produced. It says nothing about whether they worked: compare outcomes on the Performance page.">
      {items.length?<ol className="ws-bars">{items.map((item,i)=>{
        const count=finite(item.signals);
        return <li key={display(item.strategy_name,String(i))}>
          <span>{display(item.strategy_name,"Unnamed strategy")}</span><b className="num">{numberLabel(count,0)}</b>
          <i aria-hidden="true" style={{width:`${((count??0)/top*100).toFixed(1)}%`}}/>
        </li>;})}</ol>:<Empty title="No strategy produced a signal in this window."/>}
    </Card>
    <p className="ws-aside">There&rsquo;s no strategy builder or backtester in the web workspace yet. Each live setup&rsquo;s record is shown on its signals instead.</p>
  </div>;
}

function OperationsView({ data }: { data: Row }) {
  const release=record(data.release),execution=record(data.execution);
  const flag=(value:unknown, dangerOn=false)=>value===true?<Badge tone={dangerOn?"warning":"positive"}>On</Badge>:value===false?<Badge tone={dangerOn?"positive":"neutral"}>Off</Badge>:<Badge>Unknown</Badge>;
  return <div className="ws-stack"><p className="ws-aside">A healthy server doesn&rsquo;t mean it&rsquo;s ready to trade. Each control below changes only what it says, asks you to confirm, and can&rsquo;t switch on real-money trading.</p>
    <div className="ws-grid-2">
      <Card title="What's deployed"><KVList><KV label="Environment" value={display(release.environment)}/><KV label="Branch" value={display(release.branch)}/><KV label="Commit" value={<span className="mono">{display(release.commit)}</span>}/></KVList></Card>
      <Card title="Safety switches"><KVList><KV label="Real-money features" value={flag(execution.live_financial_features_enabled,true)}/><KV label="Real orders" value={flag(execution.real_execution_enabled,true)}/><KV label="Automatic orders" value={flag(execution.auto_execution_enabled,true)}/><KV label="Kill switch" value={flag(execution.kill_switch)}/></KVList></Card>
    </div></div>;
}

function StatusPanel({ state, section, onRetry, pathname }: { state: State; section: Section; onRetry: () => void; pathname: string }) {
  if (state.kind === "auth") return <div className="ui-state" role="alert"><h2>Please sign in</h2><p>Sign in to see this page. We&rsquo;ll bring you straight back.</p>
    <Link className="ui-btn ui-btn--primary" href={`/login?returnTo=${encodeURIComponent(pathname)}`}>Sign in</Link></div>;
  const restricted = state.status === 403;
  return <div className="ui-state" role="alert">
    <h2>{restricted?"Not on your plan":"This page didn't load"}</h2>
    <p>{restricted && section==="research" ? "Strategy counts are for administrators." : statusText(state.status)}</p>
    <div className="ui-actions"><button type="button" className="ui-btn" onClick={onRetry}>Try again</button>
      {restricted&&<Link className="ui-btn ui-btn--ghost" href="/app/billing">See plans</Link>}</div></div>;
}

export function WorkspaceLive({ section, signalId }: { section: Section; signalId?: string }) {
  const pathname = usePathname();
  const [state, setState] = useState<State>({kind:"loading",data:null});
  const [epoch,setEpoch] = useState(0);
  const [filters,setFilters] = useState<SignalQuery>({});
  const [signalOffset,setSignalOffset] = useState(0);

  useEffect(()=>{
    let cancelled=false;
    const load=async()=>{
      setState({kind:"loading",data:null});
      try{
        const me=await client.GET("/api/v1/platform/me");
        if(cancelled)return;
        if(!me.response.ok||!me.data){
          setState({kind:me.response.status===401?"auth":"error",data:null,status:me.response.status});return;
        }
        const user=record(record(me.data).user);
        if(section==="operations"&&user.authority!=="OWNER"&&user.authority!=="ADMIN"){
          setState({kind:"error",data:null,status:403});return;
        }
        const result=await readSection(section,signalId,filters,signalOffset);
        if(cancelled)return;
        setState(result.success?{kind:"ready",data:result.data}:{kind:result.status===401?"auth":"error",data:null,status:result.status});
      }catch{
        if(!cancelled)setState({kind:"error",data:null,status:0});
      }
    };
    void load();
    return ()=>{cancelled=true};
  },[section,signalId,filters,signalOffset,epoch]);

  // Quiet background refresh so new signals and status changes appear without
  // pressing Refresh (owner report, 9 Nov 2026: lag between channels).
  useEffect(()=>{
    if(!["signals","overview","paper","performance","notifications"].includes(section))return;
    let off=false;
    const timer=window.setInterval(async()=>{
      if(document.visibilityState!=="visible")return;
      try{
        const result=await readSection(section,signalId,filters,signalOffset);
        if(!off&&result.success)setState({kind:"ready",data:result.data});
      }catch{/* keep showing the last good data */}
    },30000);
    return ()=>{off=true;window.clearInterval(timer)};
  },[section,signalId,filters,signalOffset]);

  const refresh=()=>setEpoch(value=>value+1);
  return <>
    <header className="ws-page-head">
      <div><h1>{signalId?"Signal":titles[section]}</h1><p>{signalId?"The levels, the setup's record, and everything that happened after it was sent.":descriptions[section]}</p></div>
      <button type="button" className="ui-btn ui-btn--sm" onClick={refresh} disabled={state.kind==="loading"}>Refresh</button>
    </header>
    {section==="signals"&&!signalId&&<SignalFilters onApply={next=>{setSignalOffset(0);setFilters(next);}} />}
    {state.kind==="loading"&&<div role="status" aria-live="polite"><span className="visually-hidden">Loading…</span><Skeleton rows={3}/></div>}
    {(state.kind==="auth"||state.kind==="error")&&<StatusPanel state={state} section={section} onRetry={refresh} pathname={pathname}/>}
    {state.kind==="ready"&&state.data&&(
      section==="overview"?<OverviewView data={state.data}/>:
      section==="signals"?<SignalView data={state.data} detail={Boolean(signalId)} offset={signalOffset} onPage={signalId?undefined:setSignalOffset}/>:
      section==="paper"?<div className="ws-stack"><PaperView data={state.data}/><PaperDesk onChanged={refresh}/></div>:
      section==="portfolio"?<PortfolioView data={state.data}/>:
      section==="performance"?<PerformanceView data={state.data}/>:
      section==="research"?<ResearchView data={state.data}/>:
      section==="brokers"?<div className="ws-stack"><BrokerAccounts data={state.data} onChanged={refresh}/><DemoBrokerConnection onChanged={refresh}/></div>:
      section==="markets"?<div className="ws-stack"><MarketDirectory/><QualityView data={state.data}/></div>:
      section==="billing"?<BillingCenter data={state.data} onChanged={refresh}/>:
      section==="operations"?<div className="ws-stack"><OperationsView data={state.data}/><OwnerControls authority={display(state.data.authority,"")}/></div>:
      section==="notifications"?<div className="ws-stack"><NotificationCenter data={state.data} onChanged={refresh}/><NotificationPreferences/><DeviceNotifications/></div>:
      section==="alerts"?<AlertRules data={state.data} onChanged={refresh}/>:
      section==="watchlists"?<div className="ws-stack"><WatchlistsView data={state.data} onChanged={refresh}/><AccountCreation kind="watchlists" onCreated={refresh}/></div>:
      section==="journal"?<div className="ws-stack"><JournalView data={state.data} onChanged={refresh}/><AccountCreation kind="journal" onCreated={refresh}/></div>:
      section==="settings"?<div className="ws-stack"><TradingPreferences data={state.data} onSaved={refresh}/><AccountSecurity onChanged={refresh}/><PlanAndReferrals/><DeveloperAccess/><PrivacyCenter onChanged={refresh}/></div>:
      section==="support"?<div className="ws-stack"><SupportCenter data={state.data} onChanged={refresh}/><AccountCreation kind="support" onCreated={refresh}/></div>:
      null
    )}
  </>;
}
