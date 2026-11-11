"use client";

import { useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, finite, numberLabel, record, rows, timeLabel, type Row } from "../lib/presentation";

/** Check a trade you plan to take (10 Nov 2026), the same analysis as /check_trade in Telegram.
 *  Every check is saved and tracked; you're told how it ended, and resolved ideas feed the learning. */

const verdicts: Record<string, { label: string; tone: string }> = {
  favourable: { label: "Favourable", tone: "positive" },
  marginal: { label: "Marginal", tone: "warning" },
  unfavourable: { label: "Unfavourable", tone: "negative" },
  unrated: { label: "Not enough history", tone: "info" },
};
const outcomeLabels: Record<string, string> = {
  tp1: "Reached TP1", tp2: "Reached TP2", tp3: "Final target", sl: "Stopped out",
  missed_entry: "Entry never reached", expired: "No result in time", ambiguous: "Same-bar touch (no result)",
};

function pct(value: unknown, digits = 0): string {
  const n = finite(value);
  return n === null ? "—" : `${(n * 100).toFixed(digits)}%`;
}

type Levels = { entry: number; stop_loss: number; take_profit: number[] };

/** Advice that changes the trade (11 Nov 2026): better stop/target levels from recent history. */
function Suggestion({ data, onUse }: { data: Row; onUse?: (levels: Levels) => void }) {
  const s = record(data.suggestion);
  const advice = Array.isArray(s.advice) ? (s.advice as unknown[]).map(String) : [];
  const lockedAdvice = display(s.locked_advice, "") === "premium";
  const lockedLevels = display(s.locked_levels, "") === "vip";
  if (!advice.length && !lockedAdvice && !lockedLevels) return null;
  const tps = Array.isArray(s.take_profit) ? (s.take_profit as unknown[]).map(finite).filter((v): v is number => v !== null) : [];
  const entry = finite(s.entry), stop = finite(s.stop_loss);
  return <div className="ui-card tc-suggestion" aria-label="How to improve this trade">
    <h3>How to improve this trade</h3>
    {advice.length > 0 && <ul>{advice.map((a, i) => <li key={i}>{a}</li>)}</ul>}
    {lockedAdvice && <p className="ws-aside">A better stop and target were found for this trade. The advice is on Premium: see the <a className="ui-link" href="/pricing">plans</a>.</p>}
    {lockedLevels && <p className="ws-aside">The exact suggested stop and targets are on VIP: see the <a className="ui-link" href="/pricing">plans</a>.</p>}
    {s.changed === true && entry !== null && stop !== null && tps.length > 0 && <>
      <dl className="ui-kv">
        <div className="ui-kv-row"><dt>Suggested stop</dt><dd>{numberLabel(stop, 5)}</dd></div>
        <div className="ui-kv-row"><dt>Suggested targets</dt><dd>{tps.map(t => numberLabel(t, 5)).join(" / ")}</dd></div>
        <div className="ui-kv-row"><dt>Expected per trade (cautious)</dt><dd>{numberLabel(finite(s.expected_r_suggested), 2)}R vs {numberLabel(finite(s.expected_r_now), 2)}R now</dd></div>
      </dl>
      {onUse && <button type="button" className="ui-btn ui-btn--secondary" onClick={() => onUse({ entry, stop_loss: stop, take_profit: tps })}>Check these levels</button>}
    </>}
  </div>;
}

function Result({ data, onUse }: { data: Row; onUse?: (levels: Levels) => void }) {
  const verdict = verdicts[display(data.verdict, "unrated")] ?? verdicts.unrated;
  const hist = rows(data.historical);
  const rr = Array.isArray(data.risk_reward) ? (data.risk_reward as unknown[]).map(finite) : [];
  const ev = record(data.evidence);
  const plan = record(data.order_plan);
  const order = record(plan.order);
  return <article className="ui-card tc-result" aria-live="polite">
    <div className="ui-card-head"><div>
      <p className="ui-eyebrow">{display(data.asset)} {display(data.direction) === "long" ? "BUY" : "SELL"} · {display(data.timeframe)}</p>
      <h2>Chance of TP1 before the stop: {pct(data.probability_tp1)}</h2></div>
      <span className={`ui-badge ui-badge--${verdict.tone}`}>{verdict.label}</span></div>
    <dl className="ui-kv">
      <div className="ui-kv-row"><dt>Break-even win rate (TP1 at {numberLabel(rr[0], 2)}R)</dt><dd>{pct(data.breakeven_win_rate)}</dd></div>
      <div className="ui-kv-row"><dt>Price now</dt><dd>{numberLabel(finite(data.current_price), 5)}</dd></div>
      {order.type ? <div className="ui-kv-row"><dt>Order type</dt><dd>{display(order.type)} ({display(order.why, "")})</dd></div> : null}
      {finite(plan.stop_pips) !== null && <div className="ui-kv-row"><dt>Stop distance</dt><dd>{numberLabel(finite(plan.stop_pips), 1)} {display(plan.unit, "pips")}</dd></div>}
      {finite(plan.lots) !== null && <div className="ui-kv-row"><dt>Lots for ${numberLabel(finite(plan.risk_amount))} risk</dt><dd>{numberLabel(finite(plan.lots))}</dd></div>}
    </dl>
    {hist.length > 0 && <div className="ui-table-wrap"><table className="ui-table tc-table"><thead><tr><th>Target</th><th>R/R</th><th>Hit first</th><th>Worst case</th><th>Samples</th></tr></thead>
      <tbody>{hist.map((h, i) => <tr key={i}><th>TP{display(h.target)}</th><td>{numberLabel(rr[i], 2)}</td><td>{pct(h.rate)}</td>
        <td>{pct(h.lower_95)}</td><td>{display(h.samples)}</td></tr>)}</tbody></table></div>}
    <Suggestion data={data} onUse={onUse}/>
    {Array.isArray(data.warnings) && data.warnings.length > 0 && <ul className="tc-warnings">
      {(data.warnings as unknown[]).map((w, i) => <li key={i}>{String(w)}</li>)}</ul>}
    {Array.isArray(data.notes) && data.notes.length > 0 && <ul className="tc-notes">{(data.notes as unknown[]).map((n, i) => <li key={i}>{String(n)}</li>)}</ul>}
    {(finite(ev.engine_closed_60d) ?? 0) > 0 && <p className="ws-aside">SignalRank signals on {display(data.asset)} in the last 60 days: {display(ev.engine_closed_60d)} closed, TP1 {pct(ev.engine_tp1_rate_60d)}.</p>}
    {(finite(ev.ideas_resolved_90d) ?? 0) > 0 && <p className="ws-aside">Users&rsquo; checked ideas on {display(data.asset)} in the last 90 days: {display(ev.ideas_resolved_90d)} resolved, TP1 {pct(ev.ideas_tp1_rate_90d)}.</p>}
    <p className="ws-aside">&ldquo;Hit first&rdquo; is how often, from every recent {display(data.timeframe)} bar, price moved your target distance before your stop distance within {display(data.horizon_bars)} bars. {display(data.disclaimer, "")}</p>
    {display(data.idea_id, "") && <p className="ws-aside">Saved and tracked. You&rsquo;ll get a notification when it ends. {display(data.used_today)}/{display(data.daily_limit)} checks used today.</p>}
  </article>;
}

export function TradeCheck({ data, onChanged }: { data: Row; onChanged: () => void }) {
  const [form, setForm] = useState({ asset: "", direction: "long", entry: "", stop_loss: "", tp1: "", tp2: "", tp3: "", timeframe: "1h", notes: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Row | null>(null);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  async function check(values: typeof form) {
    setBusy(true); setError(""); setResult(null);
    try {
      const take_profit = [values.tp1, values.tp2, values.tp3].map(Number).filter(v => Number.isFinite(v) && v > 0);
      const r = await client.POST("/api/v1/platform/trade-ideas", { body: {
        asset: values.asset.trim().toUpperCase(), direction: values.direction, entry: Number(values.entry),
        stop_loss: Number(values.stop_loss), take_profit, timeframe: values.timeframe, notes: values.notes,
      } });
      if (r.response.ok && r.data) { setResult(record(r.data)); onChanged(); }
      else setError(display(record(r.error).detail, "That trade couldn't be checked. Check the numbers and try again."));
    } catch { setError("That trade couldn't be checked right now. Try again shortly."); }
    finally { setBusy(false); }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void check(form);
  }

  function applyLevels(levels: Levels) {
    const next = { ...form, entry: String(levels.entry), stop_loss: String(levels.stop_loss),
      tp1: String(levels.take_profit[0] ?? ""), tp2: String(levels.take_profit[1] ?? ""), tp3: String(levels.take_profit[2] ?? "") };
    setForm(next);
    void check(next);
  }

  const ideas = rows(data.ideas);
  return <section className="ws-stack">
    <form className="ui-card ui-form" onSubmit={submit} aria-label="Check a trade">
      <div className="ui-form-grid">
        <label className="ui-field">Instrument
          <input className="ui-input" required maxLength={32} autoComplete="off" placeholder="EURUSD, XAUUSD, BTCUSDT…" value={form.asset} onChange={set("asset")}/></label>
        <label className="ui-field">Side
          <select className="ui-select" value={form.direction} onChange={set("direction")}><option value="long">Buy</option><option value="short">Sell</option></select></label>
        <label className="ui-field">Timeframe
          <select className="ui-select" value={form.timeframe} onChange={set("timeframe")}>{["5m", "15m", "30m", "1h", "4h", "1d"].map(t => <option key={t}>{t}</option>)}</select></label>
        <label className="ui-field">Entry
          <input className="ui-input" type="number" step="any" min="0" inputMode="decimal" required value={form.entry} onChange={set("entry")}/></label>
        <label className="ui-field">Stop loss
          <input className="ui-input" type="number" step="any" min="0" inputMode="decimal" required value={form.stop_loss} onChange={set("stop_loss")}/></label>
        <label className="ui-field">Take profit 1
          <input className="ui-input" type="number" step="any" min="0" inputMode="decimal" required value={form.tp1} onChange={set("tp1")}/></label>
        <label className="ui-field">Take profit 2 (optional)
          <input className="ui-input" type="number" step="any" min="0" inputMode="decimal" value={form.tp2} onChange={set("tp2")}/></label>
        <label className="ui-field">Take profit 3 (optional)
          <input className="ui-input" type="number" step="any" min="0" inputMode="decimal" value={form.tp3} onChange={set("tp3")}/></label>
        <label className="ui-field">Notes (optional)
          <input className="ui-input" maxLength={500} value={form.notes} onChange={set("notes")} placeholder="Why you like it"/></label>
      </div>
      <div className="ui-actions"><button className="ui-btn ui-btn--primary" disabled={busy} type="submit">{busy ? "Checking…" : "Check this trade"}</button>
        <span className="ws-aside">{display(data.used_today, "0")}/{display(data.daily_limit, "—")} checks used today</span></div>
      {error && <p role="alert" className="ui-feedback ui-feedback--error">{error}</p>}
    </form>
    {result && <Result data={result} onUse={applyLevels}/>}
    <h2 className="tc-sub">Your checked ideas</h2>
    {finite(data.resolved) ? <p className="ws-aside">Resolved: {display(data.resolved)} · TP1 or better: {display(data.tp1_or_better)} ({pct(data.hit_rate)})</p> : null}
    {ideas.length ? <div className="ui-table-wrap"><table className="ui-table tc-table">
      <thead><tr><th>Instrument</th><th>Side</th><th>Entry</th><th>Estimate</th><th>Verdict</th><th>Result</th><th>Checked</th></tr></thead>
      <tbody>{ideas.map((i, n) => <tr key={n}><th>{display(i.asset)} <small>{display(i.timeframe)}</small></th>
        <td>{display(i.direction) === "long" ? "Buy" : "Sell"}</td><td>{numberLabel(finite(i.entry), 5)}</td>
        <td>{pct(i.probability)}</td><td>{verdicts[display(i.verdict, "unrated")]?.label ?? display(i.verdict)}</td>
        <td>{i.outcome ? `${outcomeLabels[display(i.outcome)] ?? display(i.outcome)}${finite(i.outcome_r) !== null ? ` (${(finite(i.outcome_r) as number) >= 0 ? "+" : ""}${numberLabel(finite(i.outcome_r), 2)}R)` : ""}` : "Tracking"}</td>
        <td>{timeLabel(i.created_at)}</td></tr>)}</tbody></table></div>
      : <div className="ui-empty"><strong>No checked trades yet.</strong><p>Fill in the form above, or send /check_trade in Telegram.</p></div>}
  </section>;
}
