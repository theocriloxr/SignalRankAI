export default function Loading() {
  return <main className="sr-global-state" role="status" aria-live="polite" aria-busy="true">
    <p className="sr-overline">SignalRankAI / Loading</p>
    <h1>Preparing the workspace.</h1>
    <p>Account and market values are retrieved from verified services, not preview estimates.</p>
    <div className="sr-global-skeleton" aria-hidden="true"><span/><span/><span/></div>
  </main>;
}
