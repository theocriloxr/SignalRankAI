"use client";

import { useEffect, useState } from "react";
import client from "../lib/client";
import { record, rows, timeLabel, type Row } from "../lib/presentation";

const classNames: Record<string, string> = { crypto: "Crypto", fx: "Forex", forex: "Forex", index: "Indices",
  stock: "Stocks", equity: "Stocks", commodity: "Commodities", other: "Other" };

function signed(value: unknown): string {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(2)}R` : "—";
}

function percent(value: unknown): string {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : "—";
}

/** Public live track record (9 Nov 2026), the same data as /track_record in Telegram. */
export function TrackRecord() {
  const [data, setData] = useState<Row | null>(null);
  const [failed, setFailed] = useState(false);
  const [range, setRange] = useState<"7d" | "30d">("30d");
  useEffect(() => {
    let off = false;
    const load = async () => {
      try {
        const r = await client.GET("/api/v1/platform/public/track-record");
        if (off) return;
        if (r.response.ok && r.data) setData(record(r.data)); else setFailed(true);
      } catch { if (!off) setFailed(true); }
    };
    void load();
    const timer = window.setInterval(() => { void load(); }, 300000);
    return () => { off = true; window.clearInterval(timer); };
  }, []);
  if (failed && !data) return <p className="tr-empty">The record is unavailable right now. Please try again shortly.</p>;
  if (!data) return <p className="tr-empty">Loading the record…</p>;
  const windows = record(data.windows);
  const classes = rows(windows[range]);
  const recent = rows(data.recent);
  return <div className="tr-body">
    <div className="tr-tabs" role="tablist" aria-label="Period">
      {(["7d", "30d"] as const).map(key => <button key={key} type="button" role="tab" aria-selected={range === key}
        className={`ui-btn ui-btn--sm${range === key ? " ui-btn--primary" : ""}`} onClick={() => setRange(key)}>
        {key === "7d" ? "Last 7 days" : "Last 30 days"}</button>)}
    </div>
    {classes.length ? <div className="tr-grid">{classes.map(c => <section key={String(c.asset_class)} className="tr-card">
      <h2>{classNames[String(c.asset_class)] ?? String(c.asset_class)}</h2>
      <p className="tr-big">{signed(c.total_r)}</p>
      <dl>
        <div><dt>Closed</dt><dd>{String(c.closed ?? 0)}</dd></div>
        <div><dt>Reached TP1</dt><dd>{String(c.reached_tp1 ?? 0)} ({percent(c.tp1_rate)})</dd></div>
        <div><dt>Stopped out</dt><dd>{String(c.stopped ?? 0)}</dd></div>
        <div><dt>Average</dt><dd>{signed(c.avg_r)}</dd></div>
      </dl>
    </section>)}</div> : <p className="tr-empty">No signal closed in this period.</p>}
    <h2 className="tr-sub">Latest closed calls</h2>
    {recent.length ? <div className="tr-table-wrap"><table className="tr-table">
      <thead><tr><th>Instrument</th><th>Side</th><th>Chart</th><th>Strategy</th><th>Result</th><th>Closed</th></tr></thead>
      <tbody>{recent.map((r, i) => <tr key={i}>
        <th>{String(r.asset ?? "")}</th><td>{String(r.direction ?? "").toUpperCase()}</td><td>{String(r.timeframe ?? "")}</td>
        <td>{String(r.strategy ?? "")}</td>
        <td className={Number(r.r) >= 0 ? "tr-up" : "tr-down"}>{signed(r.r)}</td>
        <td>{timeLabel(r.closed_at)}</td></tr>)}</tbody>
    </table></div> : <p className="tr-empty">No closed calls yet.</p>}
  </div>;
}
