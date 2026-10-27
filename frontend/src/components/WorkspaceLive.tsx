"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import client from "../lib/client";
import { AccountCreation } from "./AccountCreation";
import { SignalEvidence } from "./SignalEvidence";
import { SignalFeedback } from "./SignalFeedback";
import { NotificationCenter } from "./NotificationCenter";
import { NotificationPreferences } from "./NotificationPreferences";
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
import { SignalFilters, type SignalQuery } from "./SignalFilters";
import { Icon, type IconName } from "./ui/Icon";
import { Badge, Card, DirectionBadge, Empty, KV, KVList, Notice, Skeleton, Stat, TableWrap, type Tone } from "./ui/primitives";
import {
  display, finite, moneyLabel, numberLabel,
  probabilityLabel, record, rows, statusText, timeLabel,
  type Row,
} from "../lib/presentation";

type Section =
  | "overview" | "signals" | "markets" | "research" | "watchlists" | "alerts" | "notifications"
  | "paper" | "portfolio" | "performance" | "journal" | "brokers"
  | "billing" | "support" | "settings" | "operations";

type Outcome = { data: Row | null; status: number; success: boolean };
type State = { kind: "loading" | "ready" | "error" | "auth"; data: Row | null; status?: number };
const titles: Record<Section, string> = {
  overview: "Decision overview", signals: "Delivered signals", markets: "Market intelligence",
  research: "Strategy research", watchlists: "Watchlists", alerts: "Custom alerts", notifications: "Notifications", paper: "Paper trading",
  portfolio: "Portfolio exposure", performance: "Performance evidence", journal: "Trading journal",
  brokers: "Broker connections", billing: "Subscription and billing", support: "Support",
  settings: "Account and trading policy", operations: "Owner operations",
};
const descriptions: Record<Section, string> = {
  overview: "Your account, recent activity and the fastest routes into your workspace.",
  signals: "Signals delivered to your account, with levels, model context and recorded outcomes.",
  markets: "Search the canonical instrument registry and review signal-quality decisions.",
  research: "Which strategies have produced signals recently. Activity counts are not performance.",
  watchlists: "Follow recognised instruments. Watching never enables execution.",
  alerts: "Account-owned monitoring rules for prices, signals and provider status.",
  notifications: "Recent account notifications and the channels that deliver them.",
  paper: "Simulated positions, capital and rules. Nothing here reaches a broker.",
  portfolio: "Exposure and ledger history of your canonical paper account.",
  performance: "Outcome evidence for evaluated signals, with sample size and disclosure.",
  journal: "Personal reflections linked to signals and outcomes.",
  brokers: "Each connected account, its verified environment, policy and ledger.",
  billing: "Plans, checkout, renewal and receipts from the billing service.",
  support: "Your support conversations with the SignalRankAI team.",
  settings: "Signal preferences, identity, security, plan, developer access and privacy.",
  operations: "Owner-only, read-only release posture and execution controls.",
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

function outcomeTone(value: string): Tone {
  const v = value.toLowerCase();
  if (/(win|tp|target|profit)/.test(v)) return "positive";
  if (/(loss|sl|stop)/.test(v)) return "negative";
  if (/(open|active|pending|running)/.test(v)) return "info";
  return "neutral";
}

function SignalRecord({ signal, detail = false }: { signal: Row; detail?: boolean }) {
  const id = display(signal.signal_id, "");
  const direction = display(signal.direction, "");
  const probability = finite(signal.ml_probability_calibrated);
  const outcome = display(signal.outcome_status, "Lifecycle not reported");
  return <article className="ws-signal">
    <header className="ws-signal-head">
      <div>
        <p className="ui-eyebrow">{display(signal.asset_class, "Market")} · {display(signal.timeframe, "Timeframe unavailable")}</p>
        <h3 className="ws-signal-symbol">{display(signal.asset, "Instrument withheld")} <DirectionBadge direction={direction}/></h3>
      </div>
      <Badge tone={outcomeTone(outcome)}>{outcome}</Badge>
    </header>
    <dl className="ws-levels">
      <div className="ws-level"><dt>Entry</dt><dd>{numberLabel(signal.entry, 6)}</dd></div>
      <div className="ws-level ws-level--stop"><dt>Stop</dt><dd>{numberLabel(signal.stop_loss, 6)}</dd></div>
      <div className="ws-level ws-level--target"><dt>Target</dt><dd>{numberLabel(signal.take_profit, 6)}</dd></div>
    </dl>
    <div className="ws-signal-meta">
      <span>R/R <b>{numberLabel(signal.rr_estimate)}</b></span>
      <span>Strategy <b>{display(signal.strategy_name)}</b></span>
    </div>
    <div className="ws-prob">
      <div className="ws-signal-meta"><span>Calibrated probability <b>{probabilityLabel(signal.ml_probability_calibrated)}</b></span></div>
      {probability !== null && probability >= 0 && probability <= 1 &&
        <div className="ws-prob-bar" aria-hidden="true"><span style={{width:`${(probability*100).toFixed(1)}%`}}/></div>}
    </div>
    <footer className="ws-signal-foot"><span>Received {timeLabel(signal.delivered_at)}</span>
      {!detail && id && <Link className="ui-link" href={`/app/signals/${encodeURIComponent(id)}`}>Inspect evidence <Icon name="arrowRight"/></Link>}</footer>
  </article>;
}

function SignalView({ data, detail = false, offset = 0, onPage }: { data: Row; detail?: boolean; offset?: number; onPage?: (offset: number)=>void }) {
  if (detail) {
    const candidate = record(data.signal);
    return <div className="ws-stack">
      <Link className="ui-link" href="/app/signals"><Icon name="arrowLeft"/> All delivered signals</Link>
      <Notice tone="warning">Detail is delivered for your account only. <strong>A signal is not broker authorization or an order.</strong></Notice>
      {Object.keys(candidate).length ? <><SignalRecord signal={candidate} detail /><SignalEvidence data={data} /><SignalFeedback signalId={display(candidate.signal_id, "")} /></> : <Empty title="No entitled signal detail was returned." icon="signals"/>}
    </div>;
  }
  const items = rows(data.signals);
  return <div className="ws-stack">
    {items.length ? <div className="ws-cards">{items.map((s, i) => <SignalRecord key={display(s.signal_id, String(i))} signal={s}/>)}</div>
      : <Empty title="No delivered signals match this page." icon="signals">New signals appear only when market data, strategy and risk checks qualify. Adjust filters or check back later.</Empty>}
    {onPage&&<nav className="ui-pagination" aria-label="Signal history pages">
      <span>Page {Math.floor(offset/30)+1} · {items.length} records on this page · total count not reported</span>
      <div className="ui-actions">
        <button className="ui-btn ui-btn--sm" type="button" disabled={offset===0} onClick={()=>onPage(Math.max(0,offset-30))}><Icon name="arrowLeft"/>Previous</button>
        <button className="ui-btn ui-btn--sm" type="button" disabled={items.length<30} onClick={()=>onPage(offset+30)}>Next 30<Icon name="arrowRight"/></button>
      </div>
    </nav>}
  </div>;
}

const quickLinks: { href: string; label: string; copy: string; icon: IconName }[] = [
  { href:"/app/signals", label:"Delivered signals", copy:"Levels, model context and outcomes", icon:"signals" },
  { href:"/app/markets", label:"Market intelligence", copy:"Instrument registry and quality gates", icon:"markets" },
  { href:"/app/paper", label:"Paper desk", copy:"Practise with simulated capital", icon:"paper" },
  { href:"/app/brokers", label:"Broker connections", copy:"Verify accounts and policies", icon:"brokers" },
  { href:"/app/performance", label:"Performance", copy:"Evaluated outcomes and disclosure", icon:"performance" },
  { href:"/app/alerts", label:"Alerts", copy:"Price and signal monitoring rules", icon:"alerts" },
];

function OverviewView({ data }: { data: Row }) {
  const summary = record(data.summary), user = record(data.user), subscription = record(data.subscription);
  const name = display(user.display_name, "");
  const tier = display(subscription.tier, display(user.tier, "Plan unavailable"));
  return <div className="ws-stack">
    <section className="ws-hero-card" aria-labelledby="ws-welcome">
      <div className="ui-actions"><Badge tone="brand">{tier}</Badge><Badge tone={subscription.status==="active"?"positive":"neutral"}>{display(subscription.status, "Subscription unverified")}</Badge></div>
      <h2 id="ws-welcome">{name ? `Welcome back, ${name}.` : "Welcome back."}</h2>
      <p>New signals appear only when market data, strategy and risk checks all qualify. A quiet feed can be the correct outcome.</p>
      <div className="ui-actions"><Link className="ui-btn ui-btn--primary" href="/app/signals">Open delivered signals <Icon name="arrowRight"/></Link><Link className="ui-btn" href="/app/settings">Account settings</Link></div>
    </section>
    <div className="ui-stat-grid">
      <Stat icon="signals" label="Delivered signals" value={numberLabel(summary.delivered_signals, 0)} detail="Receipt-backed history" />
      <Stat icon="paper" label="Open paper positions" value={numberLabel(summary.open_positions, 0)} detail="Simulated orders only" />
      <Stat icon="portfolio" label="Paper cash" value={numberLabel(summary.paper_cash)} detail="Simulated units — not broker funds" />
      <Stat icon="watchlists" label="Watchlists" value={numberLabel(summary.watchlists, 0)} detail="Account-owned" />
    </div>
    <div className="ws-quick-links">{quickLinks.map(link=><Link key={link.href} href={link.href} className="ws-quick-link">
      <span className="ws-quick-icon"><Icon name={link.icon}/></span>
      <span>{link.label}<Icon name="arrowRight"/></span><small>{link.copy}</small></Link>)}</div>
    <div className="ws-grid-2">
      <Card title="Account and entitlement" eyebrow="Server-verified">
        <KVList><KV label="Plan" value={tier}/><KV label="Subscription" value={display(subscription.status, "Unverified")}/><KV label="Account" value={display(user.account_status)}/></KVList>
        <Link className="ui-link" href="/app/billing">Manage plan and billing <Icon name="arrowRight"/></Link>
      </Card>
      <Card title="Trading connections" eyebrow="Separate authorization">
        <p className="ui-card-desc">Review each broker account, its verified environment and its permissions before trading. Linking an account does not enable automatic execution.</p>
        <Link className="ui-link" href="/app/brokers">Review broker connections <Icon name="arrowRight"/></Link>
      </Card>
    </div>
  </div>;
}

function PaperView({ data }: { data: Row }) {
  const account = record(data.account), snapshot = record(data.snapshot), positions = rows(data.positions);
  const currency = account.currency;
  return <div className="ws-stack">
    <Notice tone="warning"><strong>Simulated funds only.</strong> Paper positions and P&amp;L are not proof of live broker fills.</Notice>
    <div className="ui-stat-grid">
      <Stat icon="portfolio" label="Paper cash" value={moneyLabel(account.cash_balance ?? snapshot.cash_balance, currency)} />
      <Stat icon="performance" label="Paper equity" value={moneyLabel(snapshot.equity, currency)} />
      <Stat icon="layers" label="Open paper positions" value={numberLabel(snapshot.open_positions, 0)} />
      <Stat icon="check" label="Paper realized P&L" value={moneyLabel(snapshot.realized_pnl, currency)} />
    </div>
    <Card title="Open paper positions">{positions.length ? <TableWrap label="Scrollable paper positions"><thead><tr><th>Instrument</th><th>Side</th><th>Entry</th><th>Quantity</th><th>Unrealized P&amp;L</th><th>State</th></tr></thead><tbody>{positions.map((p,i)=><tr key={display(p.position_id,String(i))}><th>{display(p.asset)}</th><td><DirectionBadge direction={display(p.direction,"")}/></td><td>{numberLabel(p.fill_entry,6)}</td><td>{numberLabel(p.quantity,6)}</td><td>{moneyLabel(p.unrealized_pnl,currency)}</td><td>{display(p.status)}</td></tr>)}</tbody></TableWrap>:<Empty title="No open paper positions." icon="paper"/>}</Card>
  </div>;
}

function PortfolioView({ data }: { data: Row }) {
  const account = record(data.account), exposures = rows(data.exposures);
  return <div className="ws-stack">
    <Notice>These values describe the canonical paper-account portfolio, not a consolidated balance across brokers.</Notice>
    <div className="ui-stat-grid"><Stat icon="portfolio" label="Paper equity" value={moneyLabel(data.equity,account.currency)}/><Stat icon="layers" label="Instruments with exposure" value={numberLabel(exposures.length,0)}/></div>
    <Card title="Instrument exposure">{exposures.length?<TableWrap label="Scrollable position exposure"><thead><tr><th>Asset</th><th>Class</th><th>Direction</th><th>Positions</th><th>Notional</th><th>Unrealized P&amp;L</th></tr></thead><tbody>{exposures.map((p,i)=><tr key={display(p.asset,String(i))+"-"+i}><th>{display(p.asset)}</th><td>{display(p.asset_class)}</td><td><DirectionBadge direction={display(p.direction,"")}/></td><td>{numberLabel(p.positions,0)}</td><td>{moneyLabel(p.notional,account.currency)}</td><td>{moneyLabel(p.unrealized_pnl,account.currency)}</td></tr>)}</tbody></TableWrap>:<Empty title="No exposures." icon="portfolio">Open paper positions will appear here grouped by instrument.</Empty>}</Card>
    <PaperEquityChart ledger={rows(data.equity_curve)} currency={account.currency}/>
  </div>;
}

/** Minimum evaluated outcomes before a ratio is shown without a small-sample warning. */
const MIN_SAMPLE = 30;

function PerformanceView({ data }: { data: Row }) {
  const summary = record(data.summary), breakdown=rows(data.breakdown);
  const sample = finite(summary.signals);
  return <div className="ws-stack">
    <Notice tone="warning">{display(summary.disclaimer,"Historical performance is not a guarantee of future results.")} Claim certified: <strong>{summary.claim_certified === true ? "yes" : "no"}</strong>.</Notice>
    {sample !== null && sample < MIN_SAMPLE && <Notice tone="neutral">Only {numberLabel(sample,0)} evaluated signals. Ratios from fewer than {MIN_SAMPLE} outcomes are statistically weak — treat them as anecdotal.</Notice>}
    <div className="ui-stat-grid"><Stat icon="signals" label="Evaluated signals" value={numberLabel(summary.signals,0)}/><Stat icon="check" label="Wins" value={numberLabel(summary.wins,0)}/><Stat icon="x" label="Losses" value={numberLabel(summary.losses,0)}/><Stat icon="performance" label="Historical win ratio" value={probabilityLabel(summary.win_rate)} detail="Not a forward performance promise"/></div>
    <Card title="Breakdown by instrument" description="Mean and total R express outcomes in multiples of the planned risk.">{breakdown.length?<TableWrap label="Scrollable performance breakdown"><thead><tr><th>Instrument</th><th>Timeframe</th><th>Signals</th><th>Mean R</th><th>Total R</th></tr></thead><tbody>{breakdown.map((p,i)=><tr key={display(p.asset,String(i))+"-"+i}><th>{display(p.asset)}</th><td>{display(p.timeframe)}</td><td>{numberLabel(p.signals,0)}</td><td>{numberLabel(p.average_r)}</td><td>{numberLabel(p.total_r)}</td></tr>)}</tbody></TableWrap>:<Empty title="No evaluated outcomes yet." icon="performance"/>}</Card>
  </div>;
}

function QualityView({ data }: { data: Row }) {
  const bucket=record(data.reject_buckets),reasons=rows(data.top_reasons);
  const categories=Object.entries(bucket).filter(([key])=>["ml","score","news","stale","slippage","other"].includes(key));
  return <Card title="Signal quality gate" eyebrow={`Last ${numberLabel(data.window_hours,0)} hours`} description="Quality decisions over the backend-reported window. Not an account return or a promised signal volume.">
    <div className="ui-stat-grid"><Stat label="Issued decisions" value={numberLabel(data.issued,0)}/><Stat label="Rejected or skipped" value={numberLabel(data.rejected_or_skipped,0)}/><Stat label="Acceptance fraction" value={probabilityLabel(data.acceptance_rate)}/></div>
    {finite(data.issued)===0&&finite(data.rejected_or_skipped)===0&&<Notice tone="warning">No quality decisions were recorded in this window. A running engine records rejections even when it issues nothing, so an empty window usually means the signal engine did not run — not that markets were quiet.</Notice>}
    <div className="ws-grid-2">
      <div className="ws-subsection"><h3>Rejection categories</h3>{categories.length?<KVList>{categories.map(([key,value])=><KV key={key} label={key} value={numberLabel(value,0)}/>)}</KVList>:<p className="ui-muted">No categories reported.</p>}</div>
      <div className="ws-subsection"><h3>Most frequent reasons</h3>{reasons.length?<KVList>{reasons.map((r,i)=><KV key={display(r.reason,String(i))} label={display(r.reason)} value={numberLabel(r.rows,0)}/>)}</KVList>:<p className="ui-muted">No rejection reasons reported.</p>}</div>
    </div>
    <QualityBreakdowns breakdowns={record(data.breakdowns)}/>
  </Card>;
}

const QUALITY_DIMENSIONS: [string,string][] = [["strategy","Strategy"],["asset","Instrument"],["timeframe","Timeframe"],["layer","Pipeline layer"]];

/** Where decisions are rejected; rows without a recorded strategy stay "(unattributed)". */
function QualityBreakdowns({ breakdowns }: { breakdowns: Row }) {
  const sections=QUALITY_DIMENSIONS.map(([key,label])=>[key,label,rows(breakdowns[key])] as const).filter(([,,items])=>items.length);
  if(!sections.length) return null;
  return <div className="ws-grid-2">{sections.map(([key,label,items])=><div className="ws-subsection" key={key}><h3>Decisions by {label.toLowerCase()}</h3><TableWrap label={`Scrollable decisions by ${label.toLowerCase()}`}><thead><tr><th>{label}</th><th>Issued</th><th>Rejected or skipped</th><th>Acceptance fraction</th></tr></thead><tbody>{items.map((item,i)=><tr key={display(item.value,String(i))+"-"+i}><th>{display(item.value)}</th><td>{numberLabel(item.issued,0)}</td><td>{numberLabel(item.rejected_or_skipped,0)}</td><td>{probabilityLabel(item.acceptance_rate)}</td></tr>)}</tbody></TableWrap></div>)}</div>;
}

function ResearchView({ data }: { data: Row }) {
  const items=rows(data.strategies);
  const top=Math.max(1,...items.map(item=>finite(item.signals)??0));
  return <Card title="Strategy activity" eyebrow={`Last ${numberLabel(data.window_days,0)} days`} description="Signals generated per strategy. Volume is not quality: compare outcomes on the Performance page.">
    {items.length?<ol className="ui-list">{items.map((item,i)=>{
      const count=finite(item.signals);
      return <li className="ui-list-row" key={display(item.strategy_name,String(i))}>
        <strong>{i+1}. {display(item.strategy_name,"Unnamed strategy")}</strong><span className="num">{numberLabel(count,0)}</span>
        {count!==null&&<small><span className="ws-prob-bar" aria-hidden="true" style={{display:"block"}}><span style={{width:`${(count/top*100).toFixed(1)}%`}}/></span></small>}
      </li>;})}</ol>:<Empty title="No strategy activity in this window." icon="research"/>}
  </Card>;
}

function OperationsView({ data }: { data: Row }) {
  const release=record(data.release),execution=record(data.execution);
  const flag=(value:unknown, dangerOn=false)=>value===true?<Badge tone={dangerOn?"warning":"positive"}>On</Badge>:value===false?<Badge tone={dangerOn?"positive":"neutral"}>Off</Badge>:<Badge>Unavailable</Badge>;
  return <div className="ws-stack"><Notice tone="warning">Owner-authorized, read-only release posture. A healthy process is not evidence of trading readiness. No kill-switch or live-money state is changed here.</Notice>
    <div className="ws-grid-2">
      <Card title="Deployed source" eyebrow="Runtime identity"><KVList><KV label="Environment" value={display(release.environment)}/><KV label="Branch" value={display(release.branch)}/><KV label="Commit" value={<span className="mono">{display(release.commit)}</span>}/></KVList></Card>
      <Card title="Execution controls" eyebrow="Safety posture"><KVList><KV label="Live financial features" value={flag(execution.live_financial_features_enabled,true)}/><KV label="Real execution" value={flag(execution.real_execution_enabled,true)}/><KV label="Automated execution" value={flag(execution.auto_execution_enabled,true)}/><KV label="Global kill switch" value={flag(execution.kill_switch)}/></KVList></Card>
    </div></div>;
}

function StatusPanel({ state, section, onRetry, pathname }: { state: State; section: Section; onRetry: () => void; pathname: string }) {
  if (state.kind === "auth") return <div className="ui-state" role="alert"><Icon name="lock"/><h2>Sign in required</h2><p>Sign in to view your account. We will bring you back to this page.</p>
    <Link className="ui-btn ui-btn--primary" href={`/login?returnTo=${encodeURIComponent(pathname)}`}>Sign in securely</Link></div>;
  const restricted = state.status === 403;
  return <div className="ui-state" role="alert"><Icon name={restricted?"lock":"warning"}/>
    <h2>{restricted?"Access restricted":"Data could not be verified"}</h2>
    <p>{restricted && section==="research" ? "Strategy research is available to administrator accounts." : statusText(state.status)}</p>
    <div className="ui-actions"><button type="button" className="ui-btn" onClick={onRetry}><Icon name="refresh"/>Retry</button>
      {restricted&&<Link className="ui-btn ui-btn--ghost" href="/app/billing">View plans</Link>}</div></div>;
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

  const refresh=()=>setEpoch(value=>value+1);
  return <>
    <header className="ws-page-head">
      <div><h1>{signalId?"Signal evidence":titles[section]}</h1><p>{descriptions[section]}</p></div>
      <button type="button" className="ui-btn" onClick={refresh} disabled={state.kind==="loading"}><Icon name="refresh"/>Refresh</button>
    </header>
    {section==="signals"&&!signalId&&<SignalFilters onApply={next=>{setSignalOffset(0);setFilters(next);}} />}
    {state.kind==="loading"&&<div role="status" aria-live="polite"><span className="visually-hidden">Checking your session and retrieving authorized records…</span><Skeleton rows={3}/></div>}
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
      section==="operations"?<OperationsView data={state.data}/>:
      section==="notifications"?<div className="ws-stack"><NotificationCenter data={state.data} onChanged={refresh}/><NotificationPreferences/></div>:
      section==="alerts"?<AlertRules data={state.data} onChanged={refresh}/>:
      section==="watchlists"?<div className="ws-stack"><WatchlistsView data={state.data} onChanged={refresh}/><AccountCreation kind="watchlists" onCreated={refresh}/></div>:
      section==="journal"?<div className="ws-stack"><JournalView data={state.data} onChanged={refresh}/><AccountCreation kind="journal" onCreated={refresh}/></div>:
      section==="settings"?<div className="ws-stack"><TradingPreferences data={state.data} onSaved={refresh}/><AccountSecurity onChanged={refresh}/><PlanAndReferrals/><DeveloperAccess/><PrivacyCenter onChanged={refresh}/></div>:
      section==="support"?<div className="ws-stack"><SupportCenter data={state.data} onChanged={refresh}/><AccountCreation kind="support" onCreated={refresh}/></div>:
      null
    )}
  </>;
}
