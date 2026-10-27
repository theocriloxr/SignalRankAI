"use client";

import Link from "next/link";

export default function ErrorBoundary({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="sr-global-state" role="alert">
    <p className="sr-overline">SignalRankAI / Recovery</p><h1>We could not complete this view.</h1>
    <p>No order, account update or payment has been confirmed by this screen. Retry, or return to the public site while services recover.</p>
    <div className="sr-global-actions">
      <button type="button" className="sr-secondary-action" onClick={reset}>Retry safely</button>
      <Link className="sr-secondary-action" href="/">Public website</Link>
    </div>
  </main>;
}
