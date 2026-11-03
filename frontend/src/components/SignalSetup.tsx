import { finite, numberLabel, record, timeLabel, type Row } from "../lib/presentation";

/** Share of the position the published plan closes at target 1 (home page: "take half off at
 * target 1"). Mirrors SIGNAL_TP1_CLOSE_FRACTION's default in core/partial_exit_accounting.py. */
const PUBLISHED_TP1_FRACTION = 0.5;

export type SetupRecord = {
  trades: number; wins: number; lowerBound: number | null; breakeven: number | null;
  lookbackDays: number | null; computedAt: string | null;
};

/** The setup's measured record, as the API returns it: ``setup_record`` on the detail response,
 * or ``segment_evidence`` carried on the signal. Null when there is none: nothing is estimated. */
export function setupRecord(source: unknown): SetupRecord | null {
  const row = record(source);
  const trades = finite(row.trades), wins = finite(row.wins);
  if (trades === null || wins === null || trades <= 0 || wins < 0 || wins > trades) return null;
  const breakeven = finite(row.breakeven), seconds = finite(row.computed_at);
  return {
    trades, wins, lowerBound: finite(row.lower_bound),
    breakeven: breakeven !== null && breakeven > 0 && breakeven < 1 ? breakeven : null,
    lookbackDays: finite(row.lookback_days),
    computedAt: seconds === null ? null : new Date(seconds * 1000).toISOString(),
  };
}

/** Break-even TP1 rate from the signal's own levels under the published plan. */
export function levelsBreakeven(signal: Row): number | null {
  const rr = finite(signal.rr_tp1);
  return rr !== null && rr > 0 ? 1 / (1 + PUBLISHED_TP1_FRACTION * rr) : null;
}

/** Whole percent, the way the Telegram card rounds. */
function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Advisory and recovery signals are stored with ``ml_recovery_mode``; they are for paper trading only. */
export function isPaperOnly(signal: Row): boolean {
  return signal.ml_recovery_mode === true || signal.ml_recovery_reason === "ml_advisory_mode";
}

export function PaperOnlyTag() {
  return <span className="ws-tag ws-tag--paper" title="The model scored this setup below its usual bar. Practise it on the paper desk.">PAPER ONLY</span>;
}

/** The Telegram card's sentence, word for word, so both channels say the same thing. */
function recordSentence(setup: SetupRecord): string {
  const days = setup.lookbackDays === null ? 60 : Math.round(setup.lookbackDays);
  const line = `Setup record (${days} days): ${numberLabel(setup.wins, 0)} of ${numberLabel(setup.trades, 0)} similar setups reached TP1 (${pct(setup.wins / setup.trades)}).`;
  return setup.breakeven === null ? line : `${line} This plan breaks even at ${pct(setup.breakeven)}.`;
}

/** One line for a signal card: the record when the signal carries one, otherwise only the
 * break-even rate its own levels imply. No placeholder for a missing record. */
export function SetupLine({ signal }: { signal: Row }) {
  const setup = setupRecord(signal.segment_evidence);
  if (setup) return <p className="ws-setup-line">{recordSentence(setup)}</p>;
  const breakeven = levelsBreakeven(signal);
  return breakeven === null ? null : <p className="ws-setup-line">This plan breaks even at <b>{pct(breakeven)}</b> of trades reaching TP1.</p>;
}

/** Detail panel for the measured record. Renders nothing when the API has no current record. */
export function SetupEvidence({ source }: { source: unknown }) {
  const setup = setupRecord(source);
  if (!setup) return null;
  return <section className="ui-card" aria-labelledby="ws-setup-title">
    <header className="ui-card-head"><div>
      <h2 className="ui-card-title" id="ws-setup-title">Setup record</h2>
      <p className="ws-setup-sentence">{recordSentence(setup)}</p>
    </div></header>
    <dl className="ws-setup-grid">
      <div><dt>Reached TP1</dt><dd>{numberLabel(setup.wins, 0)} of {numberLabel(setup.trades, 0)}</dd>
        <small>{pct(setup.wins / setup.trades)} of resolved trades for this strategy, timeframe and direction</small></div>
      {setup.lowerBound !== null && <div><dt>Cautious estimate</dt><dd>{pct(setup.lowerBound)}</dd>
        <small>The low end of a 95% range around that rate. It&rsquo;s what the filter compares</small></div>}
      {setup.breakeven !== null && <div><dt>Breaks even at</dt><dd>{pct(setup.breakeven)}</dd>
        <small>With half the position closed at TP1 and the rest protected at entry</small></div>}
    </dl>
    {setup.trades < 30 && <p className="ws-aside">That&rsquo;s only {numberLabel(setup.trades, 0)} resolved trades, so the rate can still move a long way.</p>}
    {setup.computedAt && <p className="ui-muted">Measured {timeLabel(setup.computedAt)}. This is the record as it stands now, not when the signal was sent.</p>}
  </section>;
}
