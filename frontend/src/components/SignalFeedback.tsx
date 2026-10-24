"use client";

import { useState, type FormEvent } from "react";
import client from "../lib/client";
import { Card, Feedback } from "./ui/primitives";

const issues = [
  ["", "No specific issue"], ["stale", "Arrived stale"], ["late_delivery", "Delivered late"],
  ["wrong_levels", "Levels look wrong"], ["wrong_outcome", "Outcome looks wrong"], ["bad_setup", "Weak setup"],
  ["duplicate", "Duplicate signal"], ["unclear", "Hard to understand"], ["other", "Something else"],
] as const;

/** Delivery-scoped quality feedback. The server only accepts it for signals
 * delivered to this account and never changes the signal, its outcome or any order. */
export function SignalFeedback({ signalId }: { signalId: string }) {
  const [rating, setRating] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !signalId) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const issue = String(values.get("issue") || "");
    const comment = String(values.get("comment") || "").trim();
    if (rating === null && !issue) { setResult({ ok: false, message: "Choose a rating or an issue first." }); return; }
    setBusy(true); setResult(null);
    try {
      const r = await client.POST("/api/v1/platform/signals/{signal_id}/feedback", {
        params: { path: { signal_id: signalId } },
        body: { rating, issue: issue || null, comment: comment || null },
      });
      if (r.response.ok && r.data && r.data.recorded === true) {
        setResult({ ok: true, message: "Thanks — your feedback was recorded for review." });
        form.reset(); setRating(null);
      } else setResult({ ok: false, message: r.response.status === 404 ? "Feedback is only accepted for signals delivered to your account."
        : r.response.status === 403 ? "Feedback is not available on this account." : "Feedback was not confirmed. Please retry." });
    } catch { setResult({ ok: false, message: "Feedback could not be confirmed. Please retry." }); }
    finally { setBusy(false); }
  }

  return <Card title="Rate this signal" eyebrow="Quality feedback" description="Your rating helps reviewers spot stale, duplicate or incorrect signals. It does not change the signal, its outcome or any order.">
    <form className="ui-form" onSubmit={submit}>
      <div className="ui-field"><span id="ws-rating-label">Rating</span>
        <div className="ui-segmented" role="group" aria-labelledby="ws-rating-label">
          {[1, 2, 3, 4, 5].map(value => <button key={value} type="button" aria-pressed={rating === value}
            aria-label={`${value} out of 5`} onClick={() => setRating(current => current === value ? null : value)}>{value}</button>)}
        </div>
      </div>
      <div className="ui-form-grid">
        <label className="ui-field">Issue<select className="ui-select" name="issue" defaultValue="">
          {issues.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label className="ui-field">Comment (optional)<textarea className="ui-textarea" name="comment" maxLength={4000} rows={3} placeholder="What did you notice? Never include passwords or broker keys." /></label>
      </div>
      <button type="submit" className="ui-btn" disabled={busy || !signalId}>{busy ? "Sending…" : "Send feedback"}</button>
    </form>
    {result && <Feedback error={!result.ok}>{result.message}</Feedback>}
  </Card>;
}
