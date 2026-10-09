"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import client from "../lib/client";
import { AccountCreation } from "./AccountCreation";
import { SignalEvidence } from "./SignalEvidence";
import { NotificationCenter } from "./NotificationCenter";
import { NotificationPreferences } from "./NotificationPreferences";
import { WatchlistsView } from "./WatchlistsView";
import { JournalView } from "./JournalView";
import { TradingPreferences } from "./TradingPreferences";
import { SupportCenter } from "./SupportCenter";
import { AlertRules } from "./AlertRules";
import { PaperDesk } from "./PaperDesk";
import { PaperEquityChart } from "./PaperEquityChart";
import { SignalFilters, type SignalQuery } from "./SignalFilters";
import {
  brokerMode, display, moneyLabel, numberLabel,
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
  research: "Research", watchlists: "Watchlists", alerts: "Custom alerts", notifications: "Notifications", paper: "Paper trading",
  portfolio: "Portfolio exposure", performance: "Performance evidence", journal: "Journal",
  brokers: "Broker connections", billing: "Subscription and billing", support: "Support",
  settings: "Account and trading policy", operations: "Owner operations",
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

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="sr-metric"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="sr-data-panel"><h2>{title}</h2>{children}</section>;
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return <div className="sr-data-pair"><dt>{label}</dt><dd>{value}</dd></div>;
}

function ListEmpty({ name }: { name: string }) {
  return <div className="sr-empty"><strong>No {name} returned.</strong><p>This may be the correct state. No opportunity, trade, balance or provider connection has been fabricated.</p></div>;
}

function SignalRecord({ signal }: { signal: Row }) {
  const id = display(signal.signal_id, "");
  const direction = display(signal.direction, "Unspecified").toUpperCase();
  const probability = probabilityLabel(signal.ml_probability_calibrated);
  return <article className="sr-signal-record">
    <header>
      <div><p className="sr-overline">{display(signal.asset_class, "Market")} / {display(signal.timeframe, "Timeframe unavailable")}</p>
        <h3>{display(signal.asset, "Instrument withheld")} <span className="sr-direction">{direction}</span></h3></div>
      <span className="sr-state">{display(signal.outcome_status, "Lifecycle not reported")}</span>
    </header>
    <dl className="sr-signal-levels">
      <KeyValue label="Entry" value={numberLabel(signal.entry, 6)} />
      <KeyValue label="Stop" value={numberLabel(signal.stop_loss, 6)} />
      <KeyValue label="Target" value={numberLabel(signal.take_profit, 6)} />
      <KeyValue label="R / R" value={numberLabel(signal.rr_estimate)} />
      <KeyValue label="Calibrated probability" value={probability} />
      <KeyValue label="Strategy" value={display(signal.strategy_name)} />
    </dl>
    <footer><span>Received {timeLabel(signal.delivered_at)}</span>{id && <Link href={`/app/signals/${encodeURIComponent(id)}`}>Inspect signal evidence →</Link>}</footer>
  </article>;
}

function SignalView({ data, detail = false, offset = 0, onPage }: { data: Row; detail?: boolean; offset?: number; onPage?: (offset: number)=>void }) {
  if (detail) {
    const candidate = record(data.signal);
    return <div className="sr-view-stack"><p className="sr-risk-note">Detail is delivered for your account only. A signal is not broker authorization or an order.</p>
      {Object.keys(candidate).length ? <><SignalRecord signal={candidate} /><SignalEvidence data={data} /></> : <Panel title="Signal detail"><p className="sr-muted">No entitled signal detail was returned.</p></Panel>}
      <Link className="sr-secondary-action" href="/app/signals">← Back to delivered signals</Link>
    </div>;
  }
  const items = rows(data.signals);
  return <div className="sr-view-stack">
    <p className="sr-risk-note">Only signals with canonical delivery receipts appear here. No new signals are generated by opening this view.</p>
    <div className="sr-record-grid">{items.map((s, i) => <SignalRecord key={display(s.signal_id, String(i))} signal={s}/>)}</div>
    {!items.length && <ListEmpty name="delivered signals matching this page" />}
    {onPage&&<nav className="sr-list-actions" aria-label="Signal history pages">
      <span>Page {Math.floor(offset/30)+1} · showing {items.length} records · total count not reported</span>
      <div className="sr-pagination-actions">
        <button className="sr-secondary-action" type="button" disabled={offset===0} onClick={()=>onPage(Math.max(0,offset-30))}>Previous</button>
        <button className="sr-secondary-action" type="button" disabled={items.length<30} onClick={()=>onPage(offset+30)}>Next 30</button>
      </div>
    </nav>}
  </div>;
}

function OverviewView({ data }: { data: Row }) {
  const summary = record(data.summary), user = record(data.user), subscription = record(data.subscription);
  return <div className="sr-view-stack">
    <div className="sr-metrics">
      <Metric label="Delivered signals" value={numberLabel(summary.delivered_signals, 0)} detail="Receipt-backed history" />
      <Metric label="Open paper positions" value={numberLabel(summary.open_positions, 0)} detail="Simulated orders only" />
      <Metric label="Paper cash (currency not reported)" value={numberLabel(summary.paper_cash)} detail="Paper account — NOT live broker funds; currency is not supplied by this endpoint" />
      <Metric label="Watchlists" value={numberLabel(summary.watchlists, 0)} detail="Account-owned" />
    </div>
    <div className="sr-grid-two">
      <Panel title="Account and entitlement"><dl><KeyValue label="Plan" value={display(subscription.tier, display(user.tier))}/><KeyValue label="Subscription" value={display(subscription.status, "Unverified")}/><KeyValue label="Account" value={display(user.account_status)}/></dl><Link href="/app/settings">View account settings →</Link></Panel>
      <Panel title="Execution safety"><strong className="sr-state">NOT AN EXECUTION APPROVAL</strong><p>Broker linking, demo verification, user policy and release certification are separate checks. No execution control is enabled by this dashboard.</p><Link href="/app/brokers">Review broker connections →</Link></Panel>
    </div>
    <Panel title="Today's decisions"><p>Use the canonical delivered-signal feed to review available evidence. An empty signal list can be a healthy rejection outcome.</p><Link href="/app/signals">Open delivered signals →</Link></Panel>
  </div>;
}

function PaperView({ data }: { data: Row }) {
  const account = record(data.account), snapshot = record(data.snapshot), positions = rows(data.positions);
  const currency = account.currency;
  return <div className="sr-view-stack">
    <p className="sr-risk-note">SIMULATED FUNDS ONLY — paper positions and P&amp;L are not proof of live broker fills.</p>
    <div className="sr-metrics">
      <Metric label="Paper cash" value={moneyLabel(account.cash_balance ?? snapshot.cash_balance, currency)} />
      <Metric label="Paper equity" value={moneyLabel(snapshot.equity, currency)} />
      <Metric label="Open paper positions" value={numberLabel(snapshot.open_positions, 0)} />
      <Metric label="Paper realized P&L" value={moneyLabel(snapshot.realized_pnl, currency)} />
    </div>
    <Panel title="Paper positions">{positions.length ? <div className="sr-table-scroll" tabIndex={0} aria-label="Scrollable paper positions"><table><thead><tr><th>Instrument</th><th>Side</th><th>Entry</th><th>Quantity</th><th>Unrealized P&amp;L</th><th>State</th></tr></thead><tbody>{positions.map((p,i)=><tr key={display(p.position_id,String(i))}><th>{display(p.asset)}</th><td>{display(p.direction)}</td><td>{numberLabel(p.fill_entry,6)}</td><td>{numberLabel(p.quantity,6)}</td><td>{moneyLabel(p.unrealized_pnl,currency)}</td><td>{display(p.status)}</td></tr>)}</tbody></table></div>:<ListEmpty name="paper positions"/>}</Panel>
  </div>;
}

function PortfolioView({ data }: { data: Row }) {
  const account = record(data.account), exposures = rows(data.exposures);
  return <div className="sr-view-stack">
    <p className="sr-risk-note">These values describe the canonical paper-account portfolio returned by the API, not a consolidated balance across brokers.</p>
    <div className="sr-metrics"><Metric label="Paper equity" value={moneyLabel(data.equity,account.currency)}/><Metric label="Exposures" value={numberLabel(exposures.length,0)}/></div>
    <Panel title="Instrument exposure">{exposures.length?<div className="sr-table-scroll" tabIndex={0} aria-label="Scrollable position exposure"><table><thead><tr><th>Asset</th><th>Class</th><th>Direction</th><th>Positions</th><th>Notional</th><th>Unrealized P&amp;L</th></tr></thead><tbody>{exposures.map((p,i)=><tr key={display(p.asset,String(i))+"-"+i}><th>{display(p.asset)}</th><td>{display(p.asset_class)}</td><td>{display(p.direction)}</td><td>{numberLabel(p.positions,0)}</td><td>{moneyLabel(p.notional,account.currency)}</td><td>{moneyLabel(p.unrealized_pnl,account.currency)}</td></tr>)}</tbody></table></div>:<ListEmpty name="exposures"/>}</Panel>
    <PaperEquityChart ledger={rows(data.equity_curve)} currency={account.currency}/>
  </div>;
}

function PerformanceView({ data }: { data: Row }) {
  const summary = record(data.summary), breakdown=rows(data.breakdown);
  return <div className="sr-view-stack"><p className="sr-risk-note">{display(summary.disclaimer,"Historical performance is not a guarantee of future results.")} Claim certified: {summary.claim_certified === true ? "yes" : "no"}.</p>
    <div className="sr-metrics"><Metric label="Evaluated signals" value={numberLabel(summary.signals,0)}/><Metric label="Wins" value={numberLabel(summary.wins,0)}/><Metric label="Losses" value={numberLabel(summary.losses,0)}/><Metric label="Historical win ratio" value={probabilityLabel(summary.win_rate)} detail="Not a forward performance promise"/></div>
    <Panel title="Breakdown by instrument">{breakdown.length?<div className="sr-table-scroll" tabIndex={0} aria-label="Scrollable performance breakdown"><table><thead><tr><th>Instrument</th><th>Timeframe</th><th>Signals</th><th>Mean R</th><th>Total R</th></tr></thead><tbody>{breakdown.map((p,i)=><tr key={display(p.asset,String(i))+"-"+i}><th>{display(p.asset)}</th><td>{display(p.timeframe)}</td><td>{numberLabel(p.signals,0)}</td><td>{numberLabel(p.average_r)}</td><td>{numberLabel(p.total_r)}</td></tr>)}</tbody></table></div>:<ListEmpty name="performance records"/>}</Panel>
  </div>;
}

function BrokersView({ data }: { data: Row }) {
  const connections = rows(data.connections);
  return <div className="sr-view-stack"><p className="sr-risk-note">Connecting a broker does not authorize any order. A verified account, bounded risk policy and operator release gates are required independently.</p>
    <div className="sr-record-grid">{connections.map((c,i)=><article className="sr-data-panel" key={display(c.id,String(i))}>
      <p className="sr-overline">{display(c.platform,display(c.provider))}</p><h2>{display(c.account_label, "Broker account")}</h2>
      <dl><KeyValue label="Environment" value={brokerMode(c)}/><KeyValue label="Provider status" value={display(c.status)}/><KeyValue label="Permission verification" value={c.permissions_verified===true?"Verified":c.permissions_verified===false?"Not verified":"Not reported"}/><KeyValue label="Execution" value={c.execution_enabled===true?"Enabled according to API — confirm release eligibility":"Not confirmed enabled"}/></dl>
    </article>)}</div>
    {!connections.length&&<ListEmpty name="broker connections"/>}
  </div>;
}

function BillingView({ data }: { data: Row }) {
  const subscriptions=rows(data.subscriptions), receipts=rows(data.receipts);
  return <div className="sr-view-stack">
    <p className="sr-risk-note">Subscription and receipt records are server-owned. Opening this page does not create a checkout or charge your account.</p>
    <Panel title="Automatic renewal"><dl><KeyValue label="Auto renew" value={data.auto_renew===true?"Enabled":data.auto_renew===false?"Disabled":"Unavailable"}/><KeyValue label="Provider subscription" value={data.provider_subscription_linked===true?"Linked":data.provider_subscription_linked===false?"Not linked":"Unavailable"}/></dl></Panel>
    <Panel title="Subscriptions">{subscriptions.length?<div className="sr-table-scroll" tabIndex={0} aria-label="Scrollable subscription history"><table><thead><tr><th>Plan</th><th>State</th><th>Start</th><th>Expires</th></tr></thead><tbody>{subscriptions.map((p,i)=><tr key={display(p.id,String(i))}><th>{display(p.tier)}</th><td>{display(p.status)}</td><td>{timeLabel(p.started_at)}</td><td>{timeLabel(p.expires_at)}</td></tr>)}</tbody></table></div>:<ListEmpty name="subscriptions"/>}</Panel>
    <Panel title="Confirmed receipt records">{receipts.length?<div className="sr-table-scroll" tabIndex={0} aria-label="Scrollable payment receipts"><table><thead><tr><th>Receipt</th><th>Plan</th><th>Amount</th><th>Payment state</th><th>Date</th></tr></thead><tbody>{receipts.map((r,i)=><tr key={display(r.receipt_number,String(i))}><th>{display(r.receipt_number)}</th><td>{display(r.plan)}</td><td>{moneyLabel(r.amount,r.currency)}</td><td>{display(r.status)}</td><td>{timeLabel(r.payment_date)}</td></tr>)}</tbody></table></div>:<ListEmpty name="receipts"/>}</Panel>
  </div>;
}

function QualityView({ data }: { data: Row }) {
  const bucket=record(data.reject_buckets),reasons=rows(data.top_reasons);
  return <div className="sr-view-stack">
    <p className="sr-risk-note">These are quality decisions over the backend-reported {numberLabel(data.window_hours,0)}-hour window, not an account return or a promised signal volume.</p>
    <div className="sr-metrics"><Metric label="Issued decisions" value={numberLabel(data.issued,0)}/><Metric label="Rejected or skipped" value={numberLabel(data.rejected_or_skipped,0)}/><Metric label="Acceptance fraction" value={probabilityLabel(data.acceptance_rate)}/></div>
    <Panel title="Gate rejection categories"><dl>{Object.entries(bucket).filter(([key])=>["ml","score","news","stale","slippage","other"].includes(key)).map(([key,value])=><KeyValue key={key} label={key} value={numberLabel(value,0)}/>)}</dl></Panel>
    <Panel title="Most frequent rejection reasons">{reasons.length?<div className="sr-table-scroll" tabIndex={0} aria-label="Scrollable rejection breakdown"><table><thead><tr><th>Reason</th><th>Decisions</th></tr></thead><tbody>{reasons.map((r,i)=><tr key={display(r.reason,String(i))}><th>{display(r.reason)}</th><td>{numberLabel(r.rows,0)}</td></tr>)}</tbody></table></div>:<ListEmpty name="rejection reasons"/>}</Panel>
  </div>;
}

function OperationsView({ data }: { data: Row }) {
  const release=record(data.release),execution=record(data.execution);
  const flag=(value:unknown)=>value===true?"On":value===false?"Off":"Unavailable";
  return <div className="sr-view-stack"><p className="sr-risk-note">Owner-authorized read-only release posture. A healthy process is not evidence of trading readiness. No kill-switch or live-money state is changed here.</p>
    <div className="sr-grid-two">
      <Panel title="Deployed source"><dl><KeyValue label="Environment" value={display(release.environment)}/><KeyValue label="Branch" value={display(release.branch)}/><KeyValue label="Commit" value={display(release.commit)}/></dl></Panel>
      <Panel title="Execution controls"><dl><KeyValue label="Live financial features" value={flag(execution.live_financial_features_enabled)}/><KeyValue label="Real execution" value={flag(execution.real_execution_enabled)}/><KeyValue label="Automated execution" value={flag(execution.auto_execution_enabled)}/><KeyValue label="Global kill switch" value={flag(execution.kill_switch)}/></dl></Panel>
    </div></div>;
}

function GeneralView({ section, data }: { section: Section; data: Row }) {
  const list = (
    section === "watchlists" ? rows(data.watchlists) :
    section === "alerts" ? rows(data.notifications) :
    section === "journal" ? rows(data.entries) :
    section === "support" ? rows(data.tickets) :
    section === "research" ? rows(data.strategies) : []
  );
  const facts = section==="settings" ? record(data.preferences) :
    section==="billing" ? record(data.subscription) :
    section==="operations" ? record(data) :
    section==="markets" ? record(data) : {};
  const allowed = section === "settings" ? ["trade_profile","risk_profile","min_signal_score","max_signals_per_day","session"] :
    section === "billing" ? ["tier","status","expires_at","auto_renew"] :
    section === "operations" ? ["release","readiness","engine","worker","delivery","queue","kill_switch"] :
    ["status","provider","updated_at","coverage"];
  return <div className="sr-view-stack">
    <p className="sr-risk-note">Read-only canonical information. Unreported fields remain unavailable; no settings, payments or execution permissions change here.</p>
    {allowed.some(key=>Object.hasOwn(facts,key))&&<Panel title={titles[section]}><dl>{allowed.filter(key=>Object.hasOwn(facts,key)).map(key=><KeyValue key={key} label={key.replaceAll("_"," ")} value={display(facts[key])}/>)}</dl></Panel>}
    {list.length?<div className="sr-record-grid">{list.map((item,i)=><article className="sr-data-panel" key={display(item.id,String(i))}>
      <h2>{display(item.title,display(item.name,display(item.asset,display(item.strategy_name,display(item.subject,"Item "+(i+1))))))}</h2>
      <dl><KeyValue label="State" value={display(item.status)}/><KeyValue label="Updated" value={timeLabel(item.updated_at ?? item.created_at)}/></dl>
    </article>)}</div>:<ListEmpty name={titles[section].toLowerCase()+" entries"}/>}
  </div>;
}

export function WorkspaceLive({ section, signalId }: { section: Section; signalId?: string }) {
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

  return <div className="sr-workspace-content">
    <header className="sr-workspace-heading"><div><p className="sr-overline">Canonical account workspace / {["settings","watchlists","alerts","notifications","support","journal"].includes(section)?"Account-owned controls":"Read-only records"}</p><h1>{titles[section]}</h1></div><button type="button" className="sr-secondary-action" onClick={()=>setEpoch(n=>n+1)} disabled={state.kind==="loading"}>Refresh data</button></header>
    {section==="signals"&&!signalId&&<SignalFilters onApply={next=>{setSignalOffset(0);setFilters(next);}} />}
    {state.kind==="loading"&&<div className="sr-loading" role="status" aria-live="polite">Checking your session and retrieving authorized records…</div>}
    {state.kind==="auth"&&<div className="sr-access-state" role="alert"><h2>Sign in required</h2><p>Account-specific market, signal and broker information is never shown without a valid session.</p><Link className="button" href="/login">Sign in securely</Link></div>}
    {state.kind==="error"&&<div className="sr-access-state" role="alert"><h2>{state.status===403?"Access restricted":"Data could not be verified"}</h2><p>{statusText(state.status)}</p><button className="sr-secondary-action" onClick={()=>setEpoch(n=>n+1)}>Retry</button></div>}
    {state.kind==="ready"&&state.data&&(
      section==="overview"?<OverviewView data={state.data}/>:
      section==="signals"?<SignalView data={state.data} detail={Boolean(signalId)} offset={signalOffset} onPage={signalId?undefined:setSignalOffset}/>:
      section==="paper"?<div className="sr-view-stack"><PaperView data={state.data}/><PaperDesk onChanged={()=>setEpoch(value=>value+1)}/></div>:
      section==="portfolio"?<PortfolioView data={state.data}/>:
      section==="performance"?<PerformanceView data={state.data}/>:
      section==="brokers"?<BrokersView data={state.data}/>: 
      section==="markets"?<QualityView data={state.data}/>: 
      section==="billing"?<BillingView data={state.data}/>: 
      section==="operations"?<OperationsView data={state.data}/>:
      section==="notifications"?<div className="sr-view-stack"><NotificationCenter data={state.data} onChanged={()=>setEpoch(value=>value+1)}/><NotificationPreferences/></div>:
      section==="alerts"?<AlertRules data={state.data} onChanged={()=>setEpoch(value=>value+1)}/>:
      section==="watchlists"?<div className="sr-view-stack"><WatchlistsView data={state.data} onChanged={()=>setEpoch(value=>value+1)}/><AccountCreation kind="watchlists" onCreated={()=>setEpoch(value=>value+1)}/></div>:
      section==="journal"?<div className="sr-view-stack"><JournalView data={state.data} onChanged={()=>setEpoch(value=>value+1)}/><AccountCreation kind="journal" onCreated={()=>setEpoch(value=>value+1)}/></div>:
      section==="settings"?<TradingPreferences data={state.data} onSaved={()=>setEpoch(value=>value+1)}/>:
      section==="support"?<div className="sr-view-stack"><SupportCenter data={state.data} onChanged={()=>setEpoch(value=>value+1)}/><AccountCreation kind="support" onCreated={()=>setEpoch(value=>value+1)}/></div>:
      <GeneralView section={section} data={state.data}/>
    )}
  </div>;
}
