"use client";

import { useEffect, useState } from "react";
import client from "../lib/client";
import { Card } from "./ui/primitives";

type Review = { headline?: string; why?: string[]; improve?: string[]; text?: string };
type Lesson = { text?: string };
type Lessons = { resolved_trades?: number; generated_at?: string; lessons?: Lesson[]; harmful?: Lesson[]; text?: string };

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string" && v.trim().length > 0) : [];
}

/** Why this signal worked or failed, from the lessons of every resolved trade. */
export function SignalReview({ signalId }: { signalId: string }) {
  const [review, setReview] = useState<Review | null>(null);
  useEffect(() => {
    let live = true;
    if (!signalId) return;
    client.GET("/api/v1/platform/signals/{signal_id}/review", { params: { path: { signal_id: signalId } } })
      .then((r) => { if (live && r.response.ok && r.data) setReview(r.data as Review); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [signalId]);
  if (!review) return null;
  const why = list(review.why);
  const improve = list(review.improve);
  return <Card id="ws-review" title="Why it worked — or didn't"
    description="Measured against every resolved trade the bot has tracked. A context only counts when its effect survives a multiple-testing correction.">
    {review.headline && <p><strong>{review.headline}</strong></p>}
    {why.length > 0 && <p>Why: {why.join("; ")}.</p>}
    {improve.length > 0 && <p>Next time: {improve.join("; ")}.</p>}
  </Card>;
}

/** What the bot has learned across all trades; harmful contexts are now avoided automatically. */
export function LessonsPanel() {
  const [data, setData] = useState<Lessons | null>(null);
  useEffect(() => {
    let live = true;
    client.GET("/api/v1/platform/learning/lessons", {})
      .then((r) => { if (live && r.response.ok && r.data) setData(r.data as Lessons); })
      .catch(() => undefined);
    return () => { live = false; };
  }, []);
  if (!data) return null;
  const lessons = (Array.isArray(data.lessons) ? data.lessons : []).map((l) => l?.text).filter(Boolean) as string[];
  const avoided = (Array.isArray(data.harmful) ? data.harmful : []).map((l) => l?.text).filter(Boolean) as string[];
  return <Card id="ws-lessons" title="What the bot has learned"
    description={`From ${data.resolved_trades ?? 0} resolved trades, re-checked every few hours.`}>
    {lessons.length ? <ul>{lessons.slice(0, 8).map((t, i) => <li key={i}>{t}</li>)}</ul>
      : <p>No context has a statistically reliable effect yet.</p>}
    {avoided.length > 0 && <>
      <p><strong>Now avoided automatically</strong> (still tracked, so a lesson that stops being true drops out):</p>
      <ul>{avoided.slice(0, 5).map((t, i) => <li key={i}>{t}</li>)}</ul>
    </>}
  </Card>;
}
