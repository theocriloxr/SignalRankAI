"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, finite, numberLabel, record, rows, statusText, timeLabel, type Row } from "../lib/presentation";
import { Badge, Card, Empty, Feedback, KV, KVList, Notice, Stat, TableWrap } from "./ui/primitives";

/** Owner screens for the controls added on 27–28 Oct. Presentation only: the backend
 * enforces owner authority, explicit confirmation and a recent sign-in on every change. */

const FRESH_SIGN_IN = "For your protection this needs a fresh sign-in. Sign out, sign back in, then retry within 15 minutes.";
const SCOPES = [
  { value: "strategy", label: "Strategy", example: "e.g. ORDER-BLOCK-ABC-V1" },
  { value: "instrument", label: "Instrument", example: "e.g. BTCUSDT" },
  { value: "asset_class", label: "Asset class", example: "e.g. CRYPTO" },
] as const;
type Scope = typeof SCOPES[number]["value"];

function refusal(status: number | undefined, error: unknown): string {
  const detail = record(error).detail;
  if (status === 403 && typeof detail === "string" && /recent authentication/i.test(detail)) return FRESH_SIGN_IN;
  if (status === 403) return "Only the owner account can do this.";
  if ((status === 409 || status === 422 || status === 503) && typeof detail === "string") return detail;
  return statusText(status);
}

function epochLabel(value: unknown): string {
  const n = finite(value);
  return n === null ? "Unavailable" : timeLabel(new Date(n * 1000).toISOString());
}

function usd(value: unknown): string {
  const n = finite(value);
  return n === null ? "Unavailable" : "$" + n.toFixed(n !== 0 && Math.abs(n) < 1 ? 4 : 2);
}

export function OwnerControls({ authority }: { authority: string }) {
  const owner = authority === "OWNER";
  return <div className="ws-stack">
    <ScopedKillSwitches owner={owner}/>
    <AccountMergeReview owner={owner}/>
    <AiSpend/>
  </div>;
}

function ScopedKillSwitches({ owner }: { owner: boolean }) {
  const [document, setDocument] = useState<Row | null>(null);
  const [loadError, setLoadError] = useState("");
  const [scope, setScope] = useState<Scope>("strategy");
  const [key, setKey] = useState("");
  const [reason, setReason] = useState("");
  const [phrase, setPhrase] = useState("");
  const [releasing, setReleasing] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);

  async function send(action: "status" | "on" | "off", body: { scope?: Scope; key?: string; reason?: string } = {}) {
    const result = await client.POST("/api/v1/platform/operator/kill-switch/scoped", {
      body: { action, scope: body.scope, key: body.key, reason: body.reason ?? "", confirm: action !== "status" },
    });
    if (result.response.ok && result.data) { setDocument(record(result.data)); return ""; }
    return refusal(result.response.status, result.error);
  }

  useEffect(() => {
    if (!owner) return;
    let cancelled = false;
    void client.POST("/api/v1/platform/operator/kill-switch/scoped", { body: { action: "status", reason: "", confirm: false } })
      .then(result => {
        if (cancelled) return;
        if (result.response.ok && result.data) setDocument(record(result.data));
        else setLoadError(refusal(result.response.status, result.error));
      })
      .catch(() => { if (!cancelled) setLoadError(statusText(0)); });
    return () => { cancelled = true; };
  }, [owner]);

  async function engage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    const cleanKey = key.trim(), cleanReason = reason.trim();
    if (!cleanKey || cleanReason.length < 8 || phrase !== "ENGAGE") {
      setNotice({ text: "Enter a key, a reason of at least eight characters, and type ENGAGE to confirm.", error: true });
      return;
    }
    setSaving(true); setNotice(null);
    try {
      const failure = await send("on", { scope, key: cleanKey, reason: cleanReason });
      if (failure) setNotice({ text: failure, error: true });
      else {
        setNotice({ text: `Execution is now blocked for ${scope.replace("_", " ")} ${cleanKey.toUpperCase()}. Signals still publish; only execution is stopped.`, error: false });
        setKey(""); setReason(""); setPhrase("");
      }
    } catch { setNotice({ text: "The response was interrupted. Refresh to confirm the switch state before retrying.", error: true }); }
    finally { setSaving(false); }
  }

  async function release(target: Scope, targetKey: string) {
    if (saving) return;
    setSaving(true); setNotice(null);
    try {
      const failure = await send("off", { scope: target, key: targetKey, reason: "released from the owner screen" });
      setNotice(failure ? { text: failure, error: true } : { text: `Released ${targetKey}. Other switches, including the global one, still apply.`, error: false });
      setReleasing("");
    } catch { setNotice({ text: "The response was interrupted. Refresh to confirm the switch state before retrying.", error: true }); }
    finally { setSaving(false); }
  }

  const switches = record(document?.switches);
  const engaged = SCOPES.flatMap(item => Object.entries(record(switches[item.value])).map(([name, value]) => ({ scope: item.value, label: item.label, key: name, info: record(value) })));
  const audit = rows(document?.audit).slice().reverse();
  return <Card title="Scoped kill switches" eyebrow="Execution safety"
    description="Stop execution for one strategy, instrument or asset class without stopping everything. Engaging a switch never enables trading; releasing one leaves every other control in force.">
    {!owner && <Notice tone="neutral">Only the owner account can view and change scoped kill switches.</Notice>}
    {owner && loadError && <Feedback error>{loadError} Execution stays blocked while the switch store is unreadable.</Feedback>}
    {owner && document && <>
      {engaged.length === 0 ? <Empty title="No scoped switches engaged" icon="shield">The global kill switch and per-account policies still apply.</Empty> :
        <TableWrap compact label="Engaged scoped kill switches"><thead><tr><th>Blocked</th><th>Reason</th><th><span className="visually-hidden">Action</span></th></tr></thead>
          <tbody>{engaged.map(item => {
            const id = `${item.scope}:${item.key}`;
            return <tr key={id}><th><span className="ui-eyebrow">{item.label}</span><br/><span className="mono">{item.key}</span></th>
              <td>{display(item.info.reason, "No reason recorded")}<br/><small className="ui-muted">Since {epochLabel(item.info.since)}</small></td>
              <td>{releasing === id ?
                <span className="ui-actions"><button type="button" className="ui-btn ui-btn--primary" disabled={saving} onClick={() => release(item.scope, item.key)}>{saving ? "Releasing…" : "Confirm release"}</button>
                  <button type="button" className="ui-btn" disabled={saving} onClick={() => setReleasing("")}>Cancel</button></span> :
                <button type="button" className="ui-btn" onClick={() => setReleasing(id)}>Release</button>}</td></tr>;
          })}</tbody></TableWrap>}
      <form className="ui-form" onSubmit={engage}>
        <div className="ui-form-grid">
          <label className="ui-field">Scope<select className="ui-select" value={scope} onChange={e => setScope(e.target.value as Scope)}>
            {SCOPES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label className="ui-field">Key<input className="ui-input mono" required maxLength={64} autoComplete="off" value={key}
            placeholder={SCOPES.find(item => item.value === scope)?.example} onChange={e => setKey(e.target.value)}/></label>
        </div>
        <label className="ui-field">Reason<input className="ui-input" required minLength={8} maxLength={200} value={reason}
          placeholder="Why execution must stop (no credentials)" onChange={e => setReason(e.target.value)}/></label>
        <label className="ui-field">Type ENGAGE to confirm<input className="ui-input" required autoComplete="off" value={phrase} onChange={e => setPhrase(e.target.value)}/></label>
        <div className="ui-actions"><button className="ui-btn ui-btn--primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Engage switch"}</button></div>
      </form>
      {audit.length > 0 && <details><summary>Recent changes ({audit.length})</summary>
        <TableWrap label="Scoped kill switch audit"><thead><tr><th>When</th><th>Action</th><th>Scope</th><th>Key</th><th>By</th></tr></thead>
          <tbody>{audit.map((entry, i) => <tr key={i}><td>{epochLabel(entry.at)}</td><td>{display(entry.action)}</td><td>{display(entry.scope)}</td><th className="mono">{display(entry.key)}</th><td>{display(entry.actor)}</td></tr>)}</tbody></TableWrap></details>}
    </>}
    {notice && <Feedback error={notice.error}>{notice.text}</Feedback>}
  </Card>;
}

function CountTable({ label, values, empty }: { label: string; values: unknown; empty: string }) {
  const entries = Object.entries(record(values));
  if (!entries.length) return <p className="ui-muted">{empty}</p>;
  return <TableWrap compact label={label}><thead><tr><th>Table and column</th><th>Rows</th></tr></thead>
    <tbody>{entries.map(([name, count]) => <tr key={name}><th className="mono">{name}</th><td>{typeof count === "number" ? numberLabel(count, 0) : display(count)}</td></tr>)}</tbody></TableWrap>;
}

function AccountMergeReview({ owner }: { owner: boolean }) {
  const [pending, setPending] = useState<Row[] | null>(null);
  const [listError, setListError] = useState("");
  const [selected, setSelected] = useState("");
  const [plan, setPlan] = useState<Row | null>(null);
  const [planError, setPlanError] = useState("");
  const [typed, setTyped] = useState("");
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void client.GET("/api/v1/platform/operator/account-merges").then(result => {
      if (cancelled) return;
      if (result.response.ok && result.data) { setPending(rows(record(result.data).pending)); setListError(""); }
      else setListError(refusal(result.response.status, result.error));
    }).catch(() => { if (!cancelled) setListError(statusText(0)); });
    return () => { cancelled = true; };
  }, [version]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    void client.GET("/api/v1/platform/operator/account-merges/{merge_id}", { params: { path: { merge_id: selected } } }).then(result => {
      if (cancelled) return;
      if (result.response.ok && result.data) { setPlan(record(record(result.data).plan)); setPlanError(""); }
      else { setPlan(null); setPlanError(refusal(result.response.status, result.error)); }
    }).catch(() => { if (!cancelled) { setPlan(null); setPlanError(statusText(0)); } });
    return () => { cancelled = true; };
  }, [selected]);

  function choose(id: string) {
    setPlan(null); setPlanError(""); setTyped(""); setChecked(false); setNotice(null); setSelected(id);
  }

  async function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || saving) return;
    if (!checked || typed.trim() !== selected) { setNotice({ text: "Tick the confirmation and type the merge id exactly.", error: true }); return; }
    setSaving(true); setNotice(null);
    try {
      const result = await client.POST("/api/v1/platform/operator/account-merges/{merge_id}/apply", {
        params: { path: { merge_id: selected } }, body: { confirm: true, confirm_merge_id: typed.trim() },
      });
      if (result.response.ok && result.data) {
        setNotice({ text: "Merge completed in one transaction. The person now has one account; the archived account keeps what could not move.", error: false });
        setSelected(""); setPlan(null); setTyped(""); setChecked(false); setVersion(v => v + 1);
      } else setNotice({ text: refusal(result.response.status, result.error), error: true });
    } catch { setNotice({ text: "The response was interrupted. Refresh the queue before retrying; a completed merge cannot run twice.", error: true }); }
    finally { setSaving(false); }
  }

  const failed = Object.keys(record(plan?.failed)).length > 0;
  return <Card title="Account merges awaiting review" eyebrow="Telegram ↔ web"
    description="When a web account links a Telegram identity that already has a bot account, both are kept until a reviewed merge moves the data. Preview first; nothing moves until the owner confirms."
    actions={<button type="button" className="ui-btn" onClick={() => setVersion(v => v + 1)}>Refresh queue</button>}>
    {listError && <Feedback error>{listError}</Feedback>}
    {pending !== null && pending.length === 0 && <Empty title="No merges waiting" icon="check">Linked accounts with nothing to merge complete automatically.</Empty>}
    {pending !== null && pending.length > 0 && <div className="ws-split">
      <nav className="ws-select-list" aria-label="Merges awaiting review">
        {pending.map((item, i) => {
          const id = display(item.merge_id, "");
          return <button type="button" key={id || i} disabled={!id} aria-pressed={id === selected} className="ws-select-item" onClick={() => choose(id)}>
            <span className="ui-eyebrow">Keep #{display(item.canonical_user_id)} · archive #{display(item.merged_user_id)}</span>
            <strong className="mono">{id || "Unidentified merge"}</strong>
            <small>Requested {timeLabel(item.created_at)}</small>
          </button>;
        })}
      </nav>
      <div className="ws-stack">
        {!selected && <p className="ui-muted">Select a merge to preview what would move.</p>}
        {selected && !plan && !planError && <p className="ui-loading" role="status">Building the preview…</p>}
        {planError && <Feedback error>{planError}</Feedback>}
        {plan && <>
          <KVList>
            <KV label="Kept account" value={`#${display(plan.canonical_user_id)}`}/>
            <KV label="Archived account" value={`#${display(plan.merged_user_id)}`}/>
            <KV label="Telegram identity" value={display(plan.telegram_user_id, "Not reported")}/>
          </KVList>
          {failed && <Notice tone="danger" role="alert">Part of the preview could not be computed. Do not merge until it is resolved.</Notice>}
          <h3>Moves to the kept account</h3>
          <CountTable label="Rows that would move" values={plan.movable} empty="No rows reference the archived account."/>
          <h3>Stays on the archived account</h3>
          <CountTable label="Rows kept on the archived account" values={plan.kept_on_archived_account} empty="Nothing is held back."/>
          <h3>Never moved</h3>
          <CountTable label="Rows never moved" values={plan.never_moved} empty="No protected records."/>
          {owner ? <form className="ui-form" onSubmit={apply}>
            <label className="ui-check"><input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)}/>I reviewed this preview and want to merge these accounts</label>
            <label className="ui-field">Type the merge id to confirm<input className="ui-input mono" required autoComplete="off" value={typed} onChange={e => setTyped(e.target.value)}/></label>
            <div className="ui-actions"><button className="ui-btn ui-btn--primary" type="submit" disabled={saving || failed}>{saving ? "Merging…" : "Complete merge"}</button></div>
          </form> : <Notice tone="neutral">Administrators can preview merges; only the owner can complete one.</Notice>}
        </>}
      </div>
    </div>}
    {notice && <Feedback error={notice.error}>{notice.text}</Feedback>}
  </Card>;
}

function SpendTable({ label, keyLabel, values }: { label: string; keyLabel: string; values: Row[] }) {
  if (!values.length) return null;
  return <TableWrap label={label}><thead><tr><th>{keyLabel}</th><th>Calls</th><th>Failed</th><th>Tokens in / out</th><th>Estimated cost</th></tr></thead>
    <tbody>{values.map((row, i) => <tr key={display(row.key, String(i))}><th className="mono">{display(row.key)}</th>
      <td>{numberLabel(row.calls, 0)}{finite(row.unsettled) ? ` (+${numberLabel(row.unsettled, 0)} open)` : ""}</td><td>{numberLabel(row.failed, 0)}</td>
      <td>{numberLabel(row.prompt_tokens, 0)} / {numberLabel(row.completion_tokens, 0)}</td><td>{usd(row.cost_usd)}</td></tr>)}</tbody></TableWrap>;
}

function AiSpend() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Row | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void client.GET("/api/v1/platform/operator/ai-spend", { params: { query: { days } } }).then(result => {
      if (cancelled) return;
      if (result.response.ok && result.data) { setData(record(result.data)); setError(""); }
      else { setData(null); setError(refusal(result.response.status, result.error)); }
    }).catch(() => { if (!cancelled) { setData(null); setError(statusText(0)); } });
    return () => { cancelled = true; };
  }, [days]);

  const totals = record(data?.totals);
  const budgets = rows(data?.budgets);
  const alerts = rows(data?.alerts);
  const unpriced = Array.isArray(data?.unpriced_models) ? (data?.unpriced_models as unknown[]).map(String) : [];
  return <Card title="AI spend" eyebrow="OpenAI and Gemini"
    description={display(data?.basis, "Estimated cost from the append-only usage ledger.")}
    actions={<label className="ui-field">Window<select className="ui-select" value={days} onChange={e => setDays(Number(e.target.value))}>
      {[1, 7, 30, 90].map(n => <option key={n} value={n}>{n === 1 ? "Last 24 hours" : `Last ${n} days`}</option>)}</select></label>}>
    {error && <Feedback error>{error}</Feedback>}
    {data && <>
      {data.ledger_enabled === false && <Notice tone="warning">The usage ledger is switched off, so new AI calls are not being recorded or budgeted.</Notice>}
      <div className="ws-grid-3">
        <Stat label="Estimated cost" value={usd(totals.cost_usd)} detail={`${display(data.window_days)} days`} icon="sparkle"/>
        <Stat label="Settled calls" value={numberLabel(totals.calls, 0)}/>
        <Stat label="Open reservations" value={numberLabel(totals.unsettled, 0)} detail="Counted at worst case"/>
      </div>
      {budgets.length > 0 ? <TableWrap label="AI budgets"><thead><tr><th>Scope</th><th>Period</th><th>Used</th><th>Spend / limit</th><th>Status</th></tr></thead>
        <tbody>{budgets.map((b, i) => {
          const ratio = finite(b.used_ratio);
          return <tr key={i}><th className="mono">{display(b.scope)}</th><td>{display(b.period)}</td>
            <td>{ratio === null ? "Unavailable" : <span className="ui-meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(Math.min(1, ratio) * 100)} aria-label={`${display(b.scope)} ${display(b.period)} budget used`}><span style={{ width: `${Math.min(100, ratio * 100)}%` }}/></span>}</td>
            <td>{usd(b.spend_usd)} / {usd(b.limit_usd)}</td>
            <td>{b.valid === false ? <Badge tone="negative">Invalid setting</Badge> : b.exhausted === true ? <Badge tone="negative">Exhausted</Badge> : (ratio ?? 0) >= 0.8 ? <Badge tone="warning">Near limit</Badge> : <Badge tone="positive">Within budget</Badge>}</td></tr>;
        })}</tbody></TableWrap> : <p className="ui-muted">No AI budgets are configured. Spend is recorded but not capped.</p>}
      <SpendTable label="Spend by provider" keyLabel="Provider" values={rows(data.by_provider)}/>
      <SpendTable label="Spend by workload" keyLabel="Workload" values={rows(data.by_workload)}/>
      <SpendTable label="Spend by model" keyLabel="Model" values={rows(data.by_model)}/>
      <SpendTable label="Top users by spend" keyLabel="User id" values={rows(data.by_user)}/>
      {unpriced.length > 0 && <Notice tone="warning">No price is configured for {unpriced.join(", ")}; their cost uses a deliberately high fallback.</Notice>}
      {alerts.length > 0 && <details><summary>Budget alerts ({alerts.length})</summary>
        <TableWrap label="AI budget alerts"><thead><tr><th>When</th><th>Scope</th><th>Period</th><th>Threshold</th><th>Spend / limit</th></tr></thead>
          <tbody>{alerts.map((a, i) => <tr key={i}><td>{timeLabel(a.created_at)}</td><th className="mono">{display(a.scope)}</th><td>{display(a.period)}</td>
            <td>{finite(a.threshold) === null ? "Unavailable" : `${Math.round((finite(a.threshold) ?? 0) * 100)}%`}</td><td>{usd(a.spend_usd)} / {usd(a.limit_usd)}</td></tr>)}</tbody></TableWrap></details>}
      {typeof data.pricing_note === "string" && <p className="ui-muted">{data.pricing_note}</p>}
    </>}
  </Card>;
}
