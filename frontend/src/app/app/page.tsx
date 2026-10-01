import { AppShell } from "../../components/AppShell";

export default function AppOverview() {
  return (
    <AppShell active="Overview">
      <header className="workspaceHead">
        <div><p className="eyebrow">Workspace</p><h1>Decision dashboard</h1></div>
        <span className="statusPill">FAIL-CLOSED MODE</span>
      </header>
      <div className="dashboardGrid">
        <article className="panel"><h3>Qualified signals</h3><div className="kpi">Canonical feed</div><p className="small">Only delivery-authorized signals appear in the authenticated feed.</p></article>
        <article className="panel"><h3>Market coverage</h3><div className="kpi">5 classes</div><p className="small">Crypto, FX, indices, equities, and commodities with provider-specific freshness gates.</p></article>
        <article className="panel"><h3>Execution</h3><div className="kpi">Guarded</div><p className="small">Real-money execution stays disabled until account and release certification pass.</p></article>
        <article className="panel wide"><h3>Signal lifecycle</h3><p className="small">Generation → data certification → strategy consensus → ML → risk → delivery → outcome. Open Signals to inspect canonical evidence and receipts.</p></article>
        <article className="panel"><h3>No-trade state</h3><p className="small">An empty feed can be correct when no setup clears quality, freshness, liquidity, and risk gates.</p></article>
      </div>
    </AppShell>
  );
}
