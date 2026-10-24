"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, finite, moneyLabel, numberLabel, record, rows, statusText, timeLabel, type Row } from "../lib/presentation";
import { paystackCheckoutUrl, returnedReference } from "../lib/billing";
import { Icon } from "./ui/Icon";
import { WorkspaceLink } from "./WorkspaceLink";
import { Badge, Card, Empty, Feedback, KV, KVList, Loading, Notice, TableWrap } from "./ui/primitives";

function errorDetail(error: unknown): string {
  const detail = record(error).detail;
  return typeof detail === "string" && detail.length <= 240 ? detail : "";
}

function Plans({ onError }: { onError: (message: string) => void }) {
  const [products, setProducts] = useState<Row[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [acknowledged, setAcknowledged] = useState<Record<string, boolean>>({});
  const [opening, setOpening] = useState("");

  useEffect(() => {
    let cancelled = false;
    client.GET("/api/v1/platform/billing/products").then(r => {
      if (cancelled) return;
      if (r.response.ok && r.data) setProducts(rows(record(r.data).products));
      else setLoadError(statusText(r.response.status));
    }).catch(() => { if (!cancelled) setLoadError("Plans could not be retrieved from the billing service."); });
    return () => { cancelled = true; };
  }, []);

  async function checkout(product: Row) {
    const id = display(product.product_id, "");
    if (!id || opening) return;
    const recurring = product.recurring === true;
    if (recurring && acknowledged[id] !== true) { onError("Confirm the automatic renewal terms before opening checkout."); return; }
    setOpening(id); onError("");
    try {
      const r = await client.POST("/api/v1/platform/billing/checkout", {
        body: { product_id: id, currency: "NGN", recurring_acknowledged: recurring && acknowledged[id] === true },
      });
      const destination = r.response.ok && r.data ? paystackCheckoutUrl(record(r.data).authorization_url) : null;
      if (destination) { window.location.assign(destination); return; }
      onError(r.response.status === 409 ? (errorDetail(r.error) || "Verify your email address in Settings before checkout.")
        : r.response.status === 422 ? (errorDetail(r.error) || "This plan is not currently available for checkout.")
        : r.response.status === 503 ? "Checkout is temporarily unavailable. No payment was started."
        : r.response.status === 401 ? "Your session expired. Sign in again."
        : "Checkout could not be opened safely. No payment was started.");
    } catch { onError("The billing service could not be reached. No payment was started."); }
    finally { setOpening(""); }
  }

  if (loadError) return <Notice tone="danger" role="alert">{loadError}</Notice>;
  if (products === null) return <Loading>Loading available plans…</Loading>;
  if (!products.length) return <Empty title="No plans are currently offered." icon="billing">The billing catalogue returned no active products. Contact support if you expected to see a plan.</Empty>;
  return <div className="ws-cards">{products.map(product => {
    const id = display(product.product_id, "");
    const recurring = product.recurring === true;
    const days = finite(product.duration_days);
    return <article className="ui-card" key={id}>
      <header className="ui-card-head"><div>
        <p className="ui-eyebrow">{display(product.tier, "Plan")}</p>
        <h3 className="ui-card-title">{display(product.display_name, id)}</h3>
      </div><Badge tone={recurring ? "info" : "neutral"}>{recurring ? "Auto-renews" : "One-off"}</Badge></header>
      <p className="ui-stat-value">{moneyLabel(product.price_ngn, product.currency)}</p>
      <p className="ui-muted">{days === null ? "Duration unavailable" : `${numberLabel(days, 0)} days of access`} · {display(product.renewal_disclosure, "")}</p>
      {recurring && <label className="ui-consent"><input type="checkbox" checked={acknowledged[id] === true}
        onChange={e => setAcknowledged(current => ({ ...current, [id]: e.target.checked }))} />
        <span>I understand this plan renews automatically until I cancel auto-renew.</span></label>}
      <button type="button" className="ui-btn ui-btn--primary ui-btn--block" disabled={Boolean(opening) || (recurring && acknowledged[id] !== true)} onClick={() => checkout(product)}>
        {opening === id ? "Opening secure checkout…" : <>Continue to Paystack <Icon name="external" /></>}
      </button>
    </article>;
  })}</div>;
}

function ConfirmReturn({ reference, onConfirmed }: { reference: string; onConfirmed: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  async function confirm() {
    if (busy) return;
    setBusy(true); setResult(null);
    try {
      const r = await client.POST("/api/v1/platform/billing/confirm", { body: { reference } });
      const data = record(r.data);
      if (r.response.ok && data.processed === true) {
        setResult({ ok: true, message: `Payment confirmed with Paystack. Your plan is now ${display(data.tier, "updated")}.` });
        onConfirmed();
      } else setResult({ ok: false, message: r.response.status === 409 ? (errorDetail(r.error) || "Paystack has not confirmed this payment yet. Try again shortly.")
        : r.response.status === 403 ? "This payment belongs to a different SignalRankAI account."
        : "Payment confirmation is temporarily unavailable. Nothing has been changed." });
    } catch { setResult({ ok: false, message: "The confirmation result could not be verified. Retry before contacting support." }); }
    finally { setBusy(false); }
  }
  return <Card title="Confirm your payment" eyebrow="Returned from Paystack" description="We verify the transaction directly with Paystack and check it belongs to this account before changing any access.">
    <KVList><KV label="Payment reference" value={<span className="mono">{reference}</span>} /></KVList>
    {!result?.ok && <div className="ui-actions"><button type="button" className="ui-btn ui-btn--primary" onClick={confirm} disabled={busy}><Icon name="check" />{busy ? "Verifying with Paystack…" : "Verify payment"}</button></div>}
    {result && <Feedback error={!result.ok}>{result.message}</Feedback>}
  </Card>;
}

function Renewal({ data, onChanged }: { data: Row; onChanged: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  async function cancel() {
    if (busy || !confirming) return;
    setBusy(true); setResult(null);
    try {
      const r = await client.POST("/api/v1/platform/billing/cancel-auto-renew", { body: { confirm: true } });
      if (r.response.ok && r.data) {
        setResult({ ok: true, message: display(record(r.data).policy, "Auto-renew cancellation was recorded.") });
        setConfirming(false); onChanged();
      } else setResult({ ok: false, message: r.response.status === 409 ? "There is no active paid subscription to cancel." : "Cancellation was not confirmed. Renewal settings are unchanged." });
    } catch { setResult({ ok: false, message: "The cancellation result could not be verified. Check your billing status before retrying." }); }
    finally { setBusy(false); }
  }
  const autoRenew = data.auto_renew === true ? "Enabled" : data.auto_renew === false ? "Disabled" : "Unavailable";
  return <Card title="Automatic renewal" eyebrow="Subscription">
    <KVList><KV label="Auto-renew" value={<Badge tone={data.auto_renew === true ? "info" : "neutral"}>{autoRenew}</Badge>} />
      <KV label="Provider subscription" value={data.provider_subscription_linked === true ? "Linked" : data.provider_subscription_linked === false ? "Not linked" : "Unavailable"} /></KVList>
    {data.auto_renew === true && !confirming && <button type="button" className="ui-btn" onClick={() => setConfirming(true)}>Turn off auto-renew</button>}
    {confirming && <div className="ui-confirm" role="group" aria-label="Confirm auto-renew cancellation">
      <h3>Turn off automatic renewal?</h3>
      <p>Your current paid access continues until it expires. This does not issue a refund.</p>
      <div className="ui-actions"><button type="button" className="ui-btn ui-btn--danger" disabled={busy} onClick={cancel}>{busy ? "Cancelling…" : "Confirm cancellation"}</button>
        <button type="button" className="ui-btn" disabled={busy} onClick={() => setConfirming(false)}>Keep auto-renew</button></div>
    </div>}
    {result && <Feedback error={!result.ok}>{result.message}</Feedback>}
  </Card>;
}

function RefundRequest() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const form = event.currentTarget; const values = new FormData(form);
    setBusy(true); setResult(null);
    try {
      const r = await client.POST("/api/v1/platform/billing/refund-request", { body: {
        payment_reference: String(values.get("payment_reference") || "").trim(),
        reason: String(values.get("reason") || "").trim(),
      } });
      if (r.response.ok && r.data) { setResult({ ok: true, message: "Refund review ticket created. A person will verify the payment; no automatic refund was issued." }); form.reset(); }
      else setResult({ ok: false, message: r.response.status === 404 ? "That payment reference was not found on this account." : r.response.status === 403 ? "Refund requests are not available on this account." : "The request was not confirmed. Retry or open a billing support ticket." });
    } catch { setResult({ ok: false, message: "The request could not be confirmed. Nothing was submitted." }); }
    finally { setBusy(false); }
  }
  return <Card title="Request a refund review" eyebrow="Manual review" description="Creates a billing support ticket for a payment on this account. Refunds are never automatic.">
    <form className="ui-form" onSubmit={submit}>
      <label className="ui-field">Payment reference<input className="ui-input mono" name="payment_reference" required minLength={3} maxLength={128} autoComplete="off" /></label>
      <label className="ui-field">Reason<textarea className="ui-textarea" name="reason" required minLength={3} maxLength={4000} rows={4} /></label>
      <div className="ui-actions"><button type="submit" className="ui-btn" disabled={busy}>{busy ? "Submitting…" : "Submit for review"}</button></div>
    </form>
    {result && <Feedback error={!result.ok}>{result.message}</Feedback>}
  </Card>;
}

export function BillingCenter({ data, onChanged }: { data: Row; onChanged: () => void }) {
  const subscriptions = rows(data.subscriptions), receipts = rows(data.receipts);
  const reference = returnedReference(useSearchParams().toString());
  const [checkoutError, setCheckoutError] = useState("");
  return <div className="ws-stack">
    <Notice>Prices, subscription state and receipts come from the billing service. Opening this page never charges your account; payment happens only on Paystack after you choose a plan.</Notice>
    {reference && <ConfirmReturn reference={reference} onConfirmed={onChanged} />}
    <Card title="Plans" eyebrow="Server-priced" description="Your plan controls access to features. It never overrides risk controls or authorizes live trading.">
      <Plans onError={setCheckoutError} />
      {checkoutError && <Feedback error>{checkoutError}</Feedback>}
    </Card>
    <div className="ws-grid-2">
      <Renewal data={data} onChanged={onChanged} />
      <RefundRequest />
    </div>
    <Card title="Subscription history">{subscriptions.length ? <TableWrap label="Scrollable subscription history"><thead><tr><th>Plan</th><th>State</th><th>Start</th><th>Expires</th></tr></thead><tbody>{subscriptions.map((p, i) => <tr key={display(p.id, String(i))}><th>{display(p.tier)}</th><td><Badge tone={p.status === "active" ? "positive" : "neutral"}>{display(p.status)}</Badge></td><td>{timeLabel(p.started_at)}</td><td>{timeLabel(p.expires_at)}</td></tr>)}</tbody></TableWrap> : <Empty title="No subscriptions yet." icon="billing" />}</Card>
    <Card title="Payment receipts" description="Only server-confirmed receipts are listed.">{receipts.length ? <TableWrap label="Scrollable payment receipts"><thead><tr><th>Receipt</th><th>Plan</th><th>Amount</th><th>Payment state</th><th>Date</th></tr></thead><tbody>{receipts.map((r, i) => <tr key={display(r.receipt_number, String(i))}><th className="mono">{display(r.receipt_number)}</th><td>{display(r.plan)}</td><td>{moneyLabel(r.amount, r.currency)}</td><td>{display(r.status)}</td><td>{timeLabel(r.payment_date)}</td></tr>)}</tbody></TableWrap> : <Empty title="No receipts yet." icon="billing" />}</Card>
    <p className="ui-muted">Read the <Link className="ui-link" href="/pricing">plan guide</Link> and <WorkspaceLink className="ui-link" href="/billing-policy">billing policy</WorkspaceLink>.</p>
  </div>;
}
