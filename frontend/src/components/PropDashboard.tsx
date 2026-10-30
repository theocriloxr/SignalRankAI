"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, finite, numberLabel, record, statusText, timeLabel, type Row } from "../lib/presentation";
import { Badge, Feedback, KV, KVList, Notice } from "./ui/primitives";

/** Limit usage, trading days and target progress for one account (CX-PROP-04).
 * Values come from the account's broker-proven ledger and policy; nothing is estimated here. */

function percent(value: unknown, digits = 2): string {
  const n = finite(value);
  return n === null ? "Unavailable" : `${(n * 100).toFixed(digits)}%`;
}

function Usage({ label, used, limit, ratio, help }: { label: string; used: unknown; limit: unknown; ratio: unknown; help: string }) {
  const share = finite(ratio);
  const tone = share === null ? "neutral" : share >= 1 ? "negative" : share >= 0.8 ? "warning" : "positive";
  return <div className="ws-stack">
    <div className="ui-card-head"><div><strong>{label}</strong><p className="ui-muted">{help}</p></div>
      <Badge tone={tone}>{share === null ? "Unavailable" : share >= 1 ? "Limit reached" : `${Math.round(share * 100)}% of limit`}</Badge></div>
    {share !== null && <span className="ui-meter" role="meter" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={Math.round(Math.min(1, share) * 100)} aria-label={`${label}: ${Math.round(share * 100)}% of the limit used`}>
      <span style={{ width: `${Math.min(100, share * 100)}%` }}/></span>}
    <p>{percent(used)} used of a {percent(limit)} limit</p>
  </div>;
}

export function PropDashboard({ connectionId }: { connectionId: string }) {
  const [data, setData] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const [form, setForm] = useState({ starting: "", target: "", days: "" });
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    void client.GET("/api/v1/platform/broker/connections/{connection_id}/prop-dashboard", { params: { path: { connection_id: connectionId } } })
      .then(result => {
        if (cancelled) return;
        if (result.response.ok && result.data) {
          const next = record(result.data);
          const objectives = record(next.objectives);
          setData(next); setError("");
          setForm({
            starting: display(objectives.starting_balance, ""),
            target: finite(objectives.profit_target_pct) === null ? "" : String(Number(((finite(objectives.profit_target_pct) ?? 0) * 100).toFixed(4))),
            days: display(objectives.min_trading_days, ""),
          });
        } else { setData(null); setError(result.response.status === 404 ? "" : statusText(result.response.status)); }
      })
      .catch(() => { if (!cancelled) { setData(null); setError(statusText(0)); } });
    return () => { cancelled = true; };
  }, [connectionId, version]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    const target = form.target.trim() === "" ? null : Number(form.target) / 100;
    const body = {
      starting_balance: form.starting.trim() === "" ? null : Number(form.starting),
      profit_target_pct: target,
      min_trading_days: form.days.trim() === "" ? null : Number(form.days),
    };
    if ((body.starting_balance !== null && !(body.starting_balance > 0)) || (target !== null && !(target > 0 && target <= 1))
        || (body.min_trading_days !== null && !(Number.isInteger(body.min_trading_days) && body.min_trading_days >= 0 && body.min_trading_days <= 365))) {
      setNotice({ text: "Enter a positive starting balance, a target between 0 and 100 %, and 0–365 trading days.", error: true });
      return;
    }
    setSaving(true); setNotice(null);
    try {
      const result = await client.PUT("/api/v1/platform/broker/connections/{connection_id}/prop-objectives", {
        params: { path: { connection_id: connectionId } }, body,
      });
      if (result.response.ok) { setNotice({ text: "Objectives saved. Your risk policy and certification are unchanged.", error: false }); setVersion(v => v + 1); }
      else setNotice({ text: result.response.status === 422 ? "Those values were not accepted. Check the ranges and try again." : statusText(result.response.status), error: true });
    } catch { setNotice({ text: "The save was not confirmed. Refresh before trying again.", error: true }); }
    finally { setSaving(false); }
  }

  if (error) return <section className="ui-card"><h2>Risk limit usage</h2><Feedback error>{error}</Feedback></section>;
  if (!data) return null;
  const evidence = record(data.evidence), equity = record(data.equity), daily = record(data.daily_loss), drawdown = record(data.total_drawdown);
  const days = record(data.trading_days), target = record(data.profit_target);
  const unavailable = Array.isArray(data.unavailable) ? (data.unavailable as unknown[]).map(String) : [];
  const currency = display(data.currency, "");
  const prop = data.account_mode === "PROP";
  const money = (value: unknown) => finite(value) === null ? "Unavailable" : `${numberLabel(value, 2)} ${currency}`.trim();
  const progress = finite(target.progress_of_target);
  const minimum = finite(days.minimum);
  return <>
    <section className="ui-card">
      <div className="ui-card-head"><div><p className="ui-eyebrow">Same formulas and limits as the execution gate</p><h2>Risk limit usage</h2></div>
        {evidence.stale === true ? <Badge tone="warning">Data not current</Badge> : <Badge tone="positive">Current</Badge>}</div>
      {unavailable.includes("no_equity_snapshots") && <Notice tone="neutral">No broker equity snapshots yet. Usage appears after the account reconciles; nothing is assumed meanwhile.</Notice>}
      {unavailable.includes("latest_snapshot_stale") && <Notice tone="warning">The latest equity snapshot is older than {Math.round((finite(evidence.stale_after_seconds) ?? 900) / 60)} minutes ({timeLabel(evidence.latest_snapshot_at)}). Usage may be out of date.</Notice>}
      <div className="ws-grid-2">
        <Usage label="Today's loss" used={daily.used_pct} limit={daily.limit_pct} ratio={daily.used_of_limit}
          help={`Since midnight in ${display(data.reset_timezone, "UTC")}, from equity or realized loss, whichever is larger.`}/>
        <Usage label="Total drawdown" used={drawdown.used_pct} limit={drawdown.limit_pct} ratio={drawdown.used_of_limit}
          help="From the highest equity recorded in the last 180 days."/>
      </div>
      <KVList grid>
        <KV label="Current equity" value={money(equity.current)}/>
        <KV label="Equity at day start" value={money(equity.day_start)}/>
        <KV label="Highest equity" value={money(equity.peak)}/>
        <KV label="Latest snapshot" value={timeLabel(evidence.latest_snapshot_at)}/>
      </KVList>
    </section>
    {prop && <section className="ui-card">
      <div className="ui-card-head"><div><p className="ui-eyebrow">{display(data.prop_firm, "Prop account")} · {display(data.prop_phase, "phase not set")}</p>
        <h2>Prop objectives</h2></div>
        {data.certified === true ? <Badge tone="positive">Certified</Badge> : <Badge tone="warning">Not certified</Badge>}</div>
      <KVList grid>
        <KV label="Trading days" value={`${numberLabel(days.count, 0)}${minimum === null ? "" : ` of ${numberLabel(minimum, 0)} required`}`}/>
        <KV label="Last trading day" value={display(days.last_trading_day, "None recorded")}/>
        <KV label="Starting balance" value={`${money(equity.starting)}${equity.starting_source === "first_snapshot" ? " (first snapshot)" : ""}`}/>
        <KV label="Progress" value={`${percent(target.progress_pct)}${finite(target.target_pct) === null ? "" : ` of a ${percent(target.target_pct)} target`}`}/>
      </KVList>
      {progress !== null && <span className="ui-meter" role="meter" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={Math.round(Math.min(1, progress) * 100)} aria-label={`Profit target: ${Math.round(progress * 100)}% reached`}>
        <span style={{ width: `${Math.min(100, progress * 100)}%` }}/></span>}
      {finite(target.target_pct) === null && <p className="ui-muted">No profit target set. Enter your firm&apos;s target below to track progress.</p>}
      <form className="ui-form" onSubmit={save}>
        <div className="ui-form-grid">
          <label className="ui-field">Starting balance ({currency || "account currency"})<input className="ui-input" inputMode="decimal" value={form.starting} onChange={e => setForm(f => ({ ...f, starting: e.target.value }))} placeholder="e.g. 100000"/></label>
          <label className="ui-field">Profit target (%)<input className="ui-input" inputMode="decimal" value={form.target} onChange={e => setForm(f => ({ ...f, target: e.target.value }))} placeholder="e.g. 8"/></label>
          <label className="ui-field">Minimum trading days<input className="ui-input" inputMode="numeric" value={form.days} onChange={e => setForm(f => ({ ...f, days: e.target.value }))} placeholder="e.g. 4"/></label>
        </div>
        <p className="ui-muted">From your firm&apos;s rules. Display only: these never change what orders are allowed, your risk policy or its certification.</p>
        <div className="ui-actions"><button className="ui-btn ui-btn--primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save objectives"}</button></div>
      </form>
      {notice && <Feedback error={notice.error}>{notice.text}</Feedback>}
    </section>}
  </>;
}
