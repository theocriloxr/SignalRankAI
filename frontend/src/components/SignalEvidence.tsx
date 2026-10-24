import { display, finite, numberLabel, probabilityLabel, record, rows, timeLabel, type Row } from "../lib/presentation";
import { Icon } from "./ui/Icon";
import { Badge, Card, KV, KVList, Notice, TableWrap } from "./ui/primitives";

/** Source of truth is one entitled canonical signal detail response. No fills or delivery
 * confirmations are inferred from the presence of a signal, event or channel alone. */
function EvidenceStatus({ value, proven, unknown = "Verification unavailable" }: {
  value: string; proven: unknown; unknown?: string;
}) {
  const state = proven === true ? "yes" : proven === false ? "no" : "unknown";
  return <div className="ws-evidence-flag" data-state={state}>
    <span className="ui-eyebrow">{value}</span>
    <strong><Icon name={state === "yes" ? "check" : state === "no" ? "x" : "info"}/>
      {proven === true ? "Confirmed by receipt" : proven === false ? "Not confirmed" : unknown}</strong>
  </div>;
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
  return <Card id="ws-evidence" title="Delivery, quality and lifecycle" eyebrow="Entitled evidence"
    actions={<Badge plain>Read only</Badge>}>
    <Notice tone="neutral">A receipt confirms access to this signal; it does not confirm a broker order or trade fill. Events are observation records and may not be complete.</Notice>
    <div className="ws-evidence-flags">
      <EvidenceStatus value="Account access" proven={delivered}/>
      <EvidenceStatus value="Channel receipt" proven={channelProof}/>
      <EvidenceStatus value="Execution approval" proven={undefined} unknown="Not determined by signal evidence"/>
    </div>
    <div className="ws-grid-2">
      <section className="ws-subsection">
        <h3>Delivery provenance</h3>
        <KVList>
          <KV label="Channel" value={display(proof.delivery_channel, "Not reported")}/>
          <KV label="Delivery state" value={display(proof.delivery_state)}/>
          <KV label="Receipt confirmation" value={timeLabel(proof.delivery_confirmed_at)}/>
          <KV label="Signal age on delivery" value={finite(proof.signal_age_at_delivery_seconds) === null ? "Unavailable" : `${numberLabel(proof.signal_age_at_delivery_seconds, 0)} seconds`}/>
          <KV label="Access confirmed" value={delivered === true ? "Yes" : delivered === false ? "No" : "Unavailable"}/>
        </KVList>
      </section>
      <section className="ws-subsection">
        <h3>Model and risk context</h3>
        <KVList>
          <KV label="Calibrated probability" value={probabilityLabel(signal.ml_probability_calibrated)}/>
          <KV label="Risk / reward estimate" value={numberLabel(signal.rr_estimate)}/>
          <KV label="Strategy" value={display(signal.strategy_name)}/>
          <KV label="Market regime" value={display(signal.regime)}/>
          <KV label="Model recovery mode" value={display(signal.ml_recovery_mode)}/>
          <KV label="Certified ML threshold" value={probabilityLabel(signal.ml_recovery_certified_threshold)}/>
        </KVList>
      </section>
      <section className="ws-subsection">
        <h3>Lifecycle</h3>
        <KVList>
          <KV label="State" value={display(signal.lifecycle_state)}/>
          <KV label="Entry observed" value={timeLabel(signal.entry_touched_at)}/>
          <KV label="First target" value={timeLabel(signal.tp1_hit_at)}/>
          <KV label="Stop observed" value={timeLabel(signal.sl_hit_at)}/>
          <KV label="Breakeven observed" value={timeLabel(signal.breakeven_at)}/>
          <KV label="Closure" value={timeLabel(signal.lifecycle_closed_at)}/>
          <KV label="Terminal event" value={display(signal.terminal_event_type)}/>
        </KVList>
      </section>
      <section className="ws-subsection">
        <h3>Outcome evidence</h3>
        <KVList>
          <KV label="Canonical outcome" value={display(signal.canonical_outcome)}/>
          <KV label="Outcome status" value={display(signal.outcome_status)}/>
          <KV label="Realized R multiple" value={numberLabel(signal.r_multiple, 3)}/>
          <KV label="PnL percentage" value={finite(signal.pnl_pct) === null ? "Unavailable" : `${numberLabel(signal.pnl_pct, 3)}%`}/>
          <KV label="Signal generated" value={timeLabel(signal.created_at)}/>
          <KV label="Signal expiry" value={timeLabel(signal.expires_at)}/>
        </KVList>
      </section>
    </div>
    <section className="ws-subsection" aria-labelledby="ws-evidence-events">
      <h3 id="ws-evidence-events">Recorded tracking events ({events.length})</h3>
      {events.length ? <TableWrap label="Scrollable signal event records">
        <thead><tr><th>Event time</th><th>Type</th><th>Observed price</th><th>R multiple</th></tr></thead>
        <tbody>{events.map((event, index) => <tr key={index}><td>{timeLabel(event.event_time)}</td><th>{display(event.event_type)}</th><td>{numberLabel(event.price, 6)}</td><td>{numberLabel(event.r_multiple, 3)}</td></tr>)}</tbody>
      </TableWrap> : <p className="ui-muted">No tracking events were returned for this entitled signal. This does not establish that a trade filled or closed.</p>}
    </section>
  </Card>;
}
