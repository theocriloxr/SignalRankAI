"use client";

import { useEffect, useState } from "react";
import client from "../lib/client";
import { finite, record, rows, type Row } from "../lib/presentation";
import { Badge, Card, Empty, TableWrap } from "./ui/primitives";

/** Each setup's measured record and what it allows (owner request, 8 Nov 2026).
 * A setup reaches users only while the lower bound of its TP1 rate beats the plan's break-even,
 * so "TP1 must pay at least N R" is how close each one is to signalling. */
export function SetupRecords() {
  const [data, setData] = useState<Row | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    client.GET("/api/v1/platform/setup-records")
      .then(r => { if (alive) { if (r.response.ok) setData(record(r.data)); else setFailed(true); } })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, []);
  if (failed) return null;
  const setups = rows(data?.setups);
  const pct = (v: unknown) => { const n = finite(v); return n === null ? "—" : `${(n * 100).toFixed(0)}%`; };
  return <Card title="Setup records" eyebrow={data ? `Last ${finite(data.lookback_days) ?? 60} days` : undefined}
    description="Every setup's measured record. A setup can send a signal only while the lower bound of its TP1 rate beats the break-even of the plan it publishes; the last column is the smallest TP1 reward it can carry. Setups from the strategy deck are marked.">
    {!data ? <p className="ui-muted">Loading…</p> : setups.length ? <TableWrap label="Setup records">
      <thead><tr><th>Setup</th><th>Timeframe</th><th>Side</th><th>Setups seen</th><th>Reached TP1</th><th>Lower bound</th><th>Can signal when TP1 pays</th></tr></thead>
      <tbody>{setups.map((s, i) => {
        const rr = finite(s.min_tp1_rr);
        return <tr key={`${String(s.strategy)}-${String(s.timeframe)}-${String(s.direction)}-${i}`}>
          <th>{String(s.strategy)}{s.deck_strategy === true && <> <Badge tone="info" plain>Deck</Badge></>}</th>
          <td>{String(s.timeframe)}</td><td>{String(s.direction)}</td>
          <td className="num">{finite(s.trades) ?? 0}</td><td className="num">{pct(s.tp1_rate)}</td><td className="num">{pct(s.lower_bound)}</td>
          <td>{rr === null ? <Badge tone="neutral" plain>Not yet — no record</Badge> : rr > 10 ? <Badge tone="neutral" plain>&gt; 10R</Badge> : <Badge tone={rr <= 2 ? "positive" : "neutral"} plain>{`≥ ${rr.toFixed(2)}R`}</Badge>}</td>
        </tr>;
      })}</tbody></TableWrap> : <Empty title="No setup records yet.">Records build as setups are followed forward.</Empty>}
    {data && data.current === false && <p className="ui-muted">The record snapshot is out of date; signals wait until it refreshes.</p>}
  </Card>;
}
