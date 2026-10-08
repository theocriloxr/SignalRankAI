import { display, numberLabel, probabilityLabel, record, rows, timeLabel, type Row } from "../lib/presentation";

/** Source of truth is one entitled canonical signal detail response. No fills or delivery
 * confirmations are inferred from the presence of a signal, event or channel alone. */
function EvidenceStatus({ value, proven, unknown = "Verification unavailable" }: {
  value: string; proven: unknown; unknown?: string;
}) {
  return <div className="sr-evidence-flag">
    <span className="sr-overline">{value}</span>
    <strong>{proven === true ? "Confirmed by receipt" : proven === false ? "Not confirmed" : unknown}</strong>
  </div>;
}

function Fact({ name, children }: { name: string; children: React.ReactNode }) {
  return <div className="sr-data-pair"><dt>{name}</dt><dd>{children}</dd></div>;
}

/** Explicit provenance display required before a user treats a signal as delivered. */
export function SignalEvidence({ data }: { data: Row }) {
  const signal = record(data.signal);
  const proof = record(data.proof);
  const events = rows(data.events);
  const delivered = proof.access_proven;
  const isTelegram = proof.delivery_channel === "telegram";
  const isWeb = proof.delivery_channel === "web";
  const channelProof = isTelegram ? proof.delivery_proven : isWeb ? proof.web_delivery_proven : undefined;
  return <section className="sr-data-panel sr-evidence" aria-labelledby="sr-evidence-title">
    <header className="sr-evidence-head"><div>
      <p className="sr-overline">SignalRankAI / Entitled evidence</p>
      <h2 id="sr-evidence-title">Delivery, quality and lifecycle</h2>
    </div><span className="sr-state">READ ONLY</span></header>
    <p className="sr-risk-note">A receipt confirms access to this signal; it does not confirm a broker order or trade fill. Events are observation records and may not be complete.</p>
    <div className="sr-evidence-status">
      <EvidenceStatus value="Account access" proven={delivered}/>
      <EvidenceStatus value="Channel receipt" proven={channelProof}/>
      <EvidenceStatus value="Execution approval" proven={false} unknown="Not evaluated"/>
    </div>
    <div className="sr-grid-two">
      <section className="sr-evidence-sub">
        <h3>Delivery provenance</h3>
        <dl>
          <Fact name="Channel">{display(proof.delivery_channel, "Not reported")}</Fact>
          <Fact name="Delivery state">{display(proof.delivery_state)}</Fact>
          <Fact name="Receipt confirmation">{timeLabel(proof.delivery_confirmed_at)}</Fact>
          <Fact name="Signal age on delivery">{numberLabel(proof.signal_age_at_delivery_seconds, 0)} seconds</Fact>
          <Fact name="Access confirmed">{delivered === true ? "Yes" : delivered === false ? "No" : "Unavailable"}</Fact>
        </dl>
      </section>
      <section className="sr-evidence-sub">
        <h3>Model and risk context</h3>
        <dl>
          <Fact name="Calibrated probability">{probabilityLabel(signal.ml_probability_calibrated)}</Fact>
          <Fact name="Risk / reward estimate">{numberLabel(signal.rr_estimate)}</Fact>
          <Fact name="Strategy">{display(signal.strategy_name)}</Fact>
          <Fact name="Market regime">{display(signal.regime)}</Fact>
          <Fact name="Model recovery mode">{display(signal.ml_recovery_mode)}</Fact>
          <Fact name="Certified ML threshold">{probabilityLabel(signal.ml_recovery_certified_threshold)}</Fact>
        </dl>
      </section>
    </div>
    <div className="sr-grid-two">
      <section className="sr-evidence-sub">
        <h3>Lifecycle</h3>
        <dl>
          <Fact name="State">{display(signal.lifecycle_state)}</Fact>
          <Fact name="Entry observed">{timeLabel(signal.entry_touched_at)}</Fact>
          <Fact name="First target">{timeLabel(signal.tp1_hit_at)}</Fact>
          <Fact name="Stop observed">{timeLabel(signal.sl_hit_at)}</Fact>
          <Fact name="Breakeven observed">{timeLabel(signal.breakeven_at)}</Fact>
          <Fact name="Closure">{timeLabel(signal.lifecycle_closed_at)}</Fact>
          <Fact name="Terminal event">{display(signal.terminal_event_type)}</Fact>
        </dl>
      </section>
      <section className="sr-evidence-sub">
        <h3>Outcome evidence</h3>
        <dl>
          <Fact name="Canonical outcome">{display(signal.canonical_outcome)}</Fact>
          <Fact name="Outcome status">{display(signal.outcome_status)}</Fact>
          <Fact name="Realized R multiple">{numberLabel(signal.r_multiple, 3)}</Fact>
          <Fact name="PnL percentage">{numberLabel(signal.pnl_pct, 3)}%</Fact>
          <Fact name="Signal generated">{timeLabel(signal.created_at)}</Fact>
          <Fact name="Signal expiry">{timeLabel(signal.expires_at)}</Fact>
        </dl>
      </section>
    </div>
    <section className="sr-evidence-sub" aria-labelledby="sr-evidence-events">
      <h3 id="sr-evidence-events">Recorded tracking events ({events.length})</h3>
      {events.length ? <div className="sr-table-scroll" tabIndex={0} aria-label="Scrollable signal event records"><table>
        <thead><tr><th>Event time</th><th>Type</th><th>Observed price</th><th>R multiple</th></tr></thead>
        <tbody>{events.map((event, index) => <tr key={index}><td>{timeLabel(event.event_time)}</td><th>{display(event.event_type)}</th><td>{numberLabel(event.price, 6)}</td><td>{numberLabel(event.r_multiple, 3)}</td></tr>)}</tbody>
      </table></div> : <p className="sr-muted">No tracking events were returned for this entitled signal. This does not establish that a trade filled or closed.</p>}
    </section>
  </section>;
}
