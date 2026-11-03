import { display, finite, numberLabel, priceLabel, probabilityLabel, record, riskReward, rows, targetPrices, timeLabel, type Row } from "../lib/presentation";
import { Card, KV, KVList, TableWrap } from "./ui/primitives";

/** Source of truth is one entitled canonical signal detail response. No fills or delivery
 * confirmations are inferred from the presence of a signal, event or channel alone. */
function EvidenceStatus({ value, proven, unknown = "We can't tell" }: {
  value: string; proven: unknown; unknown?: string;
}) {
  const state = proven === true ? "yes" : proven === false ? "no" : "unknown";
  return <div className="ws-evidence-flag" data-state={state}>
    <span>{value}</span>
    <strong>{proven === true ? "Confirmed" : proven === false ? "Not confirmed" : unknown}</strong>
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
  const age = finite(proof.signal_age_at_delivery_seconds);
  return <Card id="ws-evidence" title="What happened after it was sent"
    description="We record when the signal reached you and each price event we saw afterwards. A delivery record shows you got the signal; it isn't a broker order or trade fill.">
    <div className="ws-evidence-flags">
      <EvidenceStatus value="On your account" proven={delivered}/>
      <EvidenceStatus value={isTelegram ? "Delivered on Telegram" : isWeb ? "Delivered on the web" : "Delivered"} proven={channelProof}/>
      <EvidenceStatus value="Traded at a broker" proven={undefined} unknown="Not determined by signal evidence"/>
    </div>
    <div className="ws-grid-2">
      <section className="ws-subsection">
        <h3>Delivery</h3>
        <KVList>
          <KV label="Channel" value={display(proof.delivery_channel, "Not recorded")}/>
          <KV label="State" value={display(proof.delivery_state)}/>
          <KV label="Confirmed at" value={timeLabel(proof.delivery_confirmed_at)}/>
          <KV label="Age when it reached you" value={age === null ? "Unavailable" : age < 120 ? `${numberLabel(age, 0)} seconds` : `${numberLabel(age / 60, 0)} minutes`}/>
        </KVList>
      </section>
      <section className="ws-subsection">
        <h3>The setup</h3>
        <KVList>
          <KV label="Strategy" value={display(signal.strategy_name)}/>
          <KV label="Market regime" value={display(signal.regime)}/>
          <KV label="Reward to risk" value={(() => { const rr = riskReward(signal.entry, signal.stop_loss, targetPrices(signal.take_profit), signal.rr_estimate ?? signal.rr_final); return rr === null ? "Not set" : `1 : ${numberLabel(rr)}`; })()}/>
          <KV label="Model score" value={probabilityLabel(signal.ml_probability_calibrated)}/>
          <KV label="Model's usual bar" value={probabilityLabel(signal.ml_recovery_certified_threshold)}/>
        </KVList>
      </section>
      <section className="ws-subsection">
        <h3>Price path</h3>
        <KVList>
          <KV label="Current state" value={display(signal.lifecycle_state)}/>
          <KV label="Entry reached" value={timeLabel(signal.entry_touched_at)}/>
          <KV label="Target 1 reached" value={timeLabel(signal.tp1_hit_at)}/>
          <KV label="Stop moved to entry" value={timeLabel(signal.breakeven_at)}/>
          <KV label="Stop hit" value={timeLabel(signal.sl_hit_at)}/>
          <KV label="Closed" value={timeLabel(signal.lifecycle_closed_at)}/>
          <KV label="Last event" value={display(signal.terminal_event_type)}/>
        </KVList>
      </section>
      <section className="ws-subsection">
        <h3>Result</h3>
        <KVList>
          <KV label="Outcome" value={display(signal.canonical_outcome, display(signal.outcome_status, "No result yet"))}/>
          <KV label="Result in R" value={numberLabel(signal.r_multiple, 2)}/>
          <KV label="Result in %" value={finite(signal.pnl_pct) === null ? "Unavailable" : `${numberLabel(signal.pnl_pct, 2)}%`}/>
          <KV label="Created" value={timeLabel(signal.created_at)}/>
          <KV label="Expires" value={timeLabel(signal.expires_at)}/>
        </KVList>
      </section>
    </div>
    <section className="ws-subsection" aria-labelledby="ws-evidence-events">
      <h3 id="ws-evidence-events">Price events ({events.length})</h3>
      {events.length ? <TableWrap label="Price events for this signal">
        <thead><tr><th>Time</th><th>Event</th><th>Price</th><th>R at that point</th></tr></thead>
        <tbody>{events.map((event, index) => <tr key={index}><td>{timeLabel(event.event_time)}</td><th>{display(event.event_type)}</th><td>{priceLabel(event.price)}</td><td>{numberLabel(event.r_multiple, 2)}</td></tr>)}</tbody>
      </TableWrap> : <p className="ui-muted">No price events recorded yet.</p>}
    </section>
  </Card>;
}
