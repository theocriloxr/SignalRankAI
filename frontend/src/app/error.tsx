"use client";

import Link from "next/link";
import { Icon } from "../components/ui/Icon";

export default function ErrorBoundary({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="global-state" role="alert">
    <span className="ui-badge ui-badge--warning">Recovery</span>
    <h1>We could not complete this view.</h1>
    <p>No order, account update or payment has been confirmed by this screen. Retry, or return to the public site while services recover.</p>
    <div className="ui-actions">
      <button type="button" className="ui-btn ui-btn--primary" onClick={reset}><Icon name="refresh"/>Retry safely</button>
      <Link className="ui-btn" href="/">Public website</Link>
    </div>
  </main>;
}
