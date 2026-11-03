import { finite, numberLabel, probabilityLabel, record, type Row } from "../lib/presentation";

/** Share of the position the published plan closes at target 1 (home page: "take half off at
 * target 1"). Mirrors SIGNAL_TP1_CLOSE_FRACTION's default in core/partial_exit_accounting.py. */
const PUBLISHED_TP1_FRACTION = 0.5;

export type SetupRecord = {
  trades: number | null; wins: number | null; lowerBound: number | null;
  breakeven: number | null; breakevenSource: "filter" | "levels" | null;
};

/** The setup filter's numbers when the signal carries them (``segment_evidence``); otherwise the
 * break-even rate worked out from the signal's own target-1 reward/risk. Nothing is estimated
 * for the record itself: an absent record stays absent. */
export function setupRecord(signal: Row): SetupRecord {
  const evidence = record(signal.segment_evidence);
  const trades = finite(evidence.trades), wins = finite(evidence.wins);
  const lowerBound = finite(evidence.lower_bound);
  const filterBreakeven = finite(evidence.breakeven);
  if (filterBreakeven !== null && filterBreakeven > 0 && filterBreakeven < 1) {
    return { trades, wins, lowerBound, breakeven: filterBreakeven, breakevenSource: "filter" };
  }
  const rr = finite(signal.rr_tp1);
  const breakeven = rr !== null && rr > 0 ? 1 / (1 + PUBLISHED_TP1_FRACTION * rr) : null;
  return { trades, wins, lowerBound, breakeven, breakevenSource: breakeven === null ? null : "levels" };
}

/** Advisory and recovery signals are stored with ``ml_recovery_mode``; they are for paper trading only. */
export function isPaperOnly(signal: Row): boolean {
  return signal.ml_recovery_mode === true || signal.ml_recovery_reason === "ml_advisory_mode";
}

export function PaperOnlyTag() {
  return <span className="ws-tag ws-tag--paper" title="The model scored this setup below its usual bar. Practise it on the paper desk.">PAPER ONLY</span>;
}

/** One-line summary for a signal card. */
export function SetupLine({ signal }: { signal: Row }) {
  const setup = setupRecord(signal);
  const hasRecord = setup.trades !== null && setup.wins !== null && setup.trades > 0;
  return <p className="ws-setup-line">
    {hasRecord
      ? <>Setup record: <b>{numberLabel(setup.wins, 0)} of {numberLabel(setup.trades, 0)}</b> reached target 1 in the last 60 days</>
      : <>Setup record not attached to this signal</>}
    {setup.breakeven !== null && <> · needs <b>{probabilityLabel(setup.breakeven)}</b> to break even</>}
  </p>;
}

/** Detail panel: the record, the cautious estimate, and what this trade needs. */
export function SetupEvidence({ signal }: { signal: Row }) {
  const setup = setupRecord(signal);
  const hasRecord = setup.trades !== null && setup.wins !== null && setup.trades > 0;
  const raw = hasRecord ? (setup.wins as number) / (setup.trades as number) : null;
  const locked = signal.exact_levels_locked === true;
  return <section className="ui-card" aria-labelledby="ws-setup-title">
    <header className="ui-card-head"><div>
      <h2 className="ui-card-title" id="ws-setup-title">Why this was sent</h2>
      <p className="ui-card-desc">A setup is one strategy on one timeframe in one direction. We send a signal only when the
        cautious end of the setup&rsquo;s 60-day hit rate for target 1 is above the rate this trade needs to break even.</p>
    </div>{isPaperOnly(signal) && <PaperOnlyTag/>}</header>
    <dl className="ws-setup-grid">
      <div><dt>Reached target 1</dt><dd>{hasRecord ? `${numberLabel(setup.wins, 0)} of ${numberLabel(setup.trades, 0)}` : "Not attached"}</dd>
        <small>{raw === null ? "This signal was stored without its setup record." : `${probabilityLabel(raw)} of resolved trades in 60 days`}</small></div>
      <div><dt>Cautious estimate</dt><dd>{setup.lowerBound === null ? "Not attached" : probabilityLabel(setup.lowerBound)}</dd>
        <small>Lower end of a 95% range, so a small sample can&rsquo;t look better than it has shown</small></div>
      <div><dt>Needed to break even</dt><dd>{locked && setup.breakeven === null ? "Paid plans" : probabilityLabel(setup.breakeven)}</dd>
        <small>{setup.breakevenSource === "filter" ? "As used by the filter when this signal was sent"
          : setup.breakevenSource === "levels" ? "From this signal's target 1 and stop, with half the position closed at target 1"
          : "Needs the entry, stop and target 1 levels"}</small></div>
    </dl>
    {hasRecord && setup.trades !== null && setup.trades < 30 && <p className="ws-aside">Only {numberLabel(setup.trades, 0)} resolved trades back this setup. Expect the real hit rate to move as more close.</p>}
    {isPaperOnly(signal) && <p className="ws-aside">The model scored this one below its usual bar, so it&rsquo;s for paper trading only. Try it on the paper desk before risking money on setups like it.</p>}
  </section>;
}
