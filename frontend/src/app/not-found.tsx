import Link from "next/link";

export default function NotFound() {
  return <main className="global-state">
    <span className="ui-badge">404</span>
    <h1>This page is unavailable.</h1>
    <p>The address may have changed. Private signal and broker references are not exposed when a route cannot be verified.</p>
    <div className="ui-actions"><Link className="ui-btn ui-btn--primary" href="/">Public website</Link><Link className="ui-btn" href="/app">Workspace</Link></div>
  </main>;
}
