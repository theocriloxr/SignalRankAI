import Link from "next/link";
export default function NotFound() {
  return <main className="sr-global-state">
    <p className="sr-overline">404 / SignalRankAI</p><h1>This route is unavailable.</h1>
    <p>The address may have changed. Private signal and broker references are not exposed when a route cannot be verified.</p>
    <div className="sr-global-actions"><Link className="sr-secondary-action" href="/">Public website</Link><Link className="sr-secondary-action" href="/app">Workspace</Link></div>
  </main>;
}
