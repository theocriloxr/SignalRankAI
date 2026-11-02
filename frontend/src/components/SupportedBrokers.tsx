"use client";

import { useEffect, useState } from "react";
import client from "../lib/client";
import { display, record, rows, type Row } from "../lib/presentation";

const ADAPTER_LABEL: Record<string, string> = {
  ready: "Execution adapter ready",
  integration: "Connection only (execution in progress)",
  connection_only: "Connection only",
  custom: "Custom integration",
};

/** Supported platforms from GET /broker/platforms. Readiness describes the code path;
 * live execution still needs the owner's activation and per-account approval. */
export function SupportedBrokers() {
  const [platforms, setPlatforms] = useState<Row[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    client.GET("/api/v1/platform/broker/platforms").then(result => {
      if (!cancelled) setPlatforms(result.response.ok && result.data ? rows(record(result.data).platforms) : []);
    }).catch(() => { if (!cancelled) setPlatforms([]); });
    return () => { cancelled = true; };
  }, []);
  if (!platforms || platforms.length === 0) return null;
  return <section className="ui-card" aria-labelledby="supported-brokers">
    <p className="ui-eyebrow">Brokers and exchanges</p>
    <h2 id="supported-brokers">Supported platforms</h2>
    <p className="ui-muted">Any MetaTrader 4/5 broker works (Exness, AssexMarkets, IC Markets, Pepperstone, prop firms…); each account&apos;s own symbol names are matched automatically. Connecting never enables live trading by itself.</p>
    <ul className="ws-broker-grid">
      {platforms.map(p => {
        const brokers = rows(p.popular_brokers);
        const classes = Array.isArray(p.asset_classes) ? p.asset_classes.map(String).join(", ") : "";
        return <li key={display(p.platform, "")} className="ws-broker-item">
          <strong>{display(p.name)}</strong>
          <span className="ui-badge" data-tone={p.execution_adapter === "ready" ? "positive" : "neutral"}>
            {ADAPTER_LABEL[String(p.execution_adapter)] || display(p.execution_adapter)}</span>
          {classes && <small>{classes}</small>}
          {p.demo_supported === true && <small>Demo accounts supported</small>}
          {brokers.length > 0 && <details className="ws-broker-details">
            <summary>Popular brokers ({brokers.length})</summary>
            <ul className="ws-broker-hints">{brokers.map(b => <li key={display(b.name, "")}>
              <b>{display(b.name)}</b> — {display(b.server_hint, "")}{b.symbol_note ? ` · ${display(b.symbol_note, "")}` : ""}
            </li>)}</ul>
          </details>}
          {typeof p.note === "string" && p.note && <small className="ui-muted">{p.note}</small>}
        </li>;
      })}
    </ul>
  </section>;
}
