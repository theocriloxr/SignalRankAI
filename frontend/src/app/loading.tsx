export default function Loading() {
  return <main className="global-state" role="status" aria-live="polite" aria-busy="true">
    <span className="ui-badge ui-badge--brand">Loading</span>
    <h1>Preparing your view.</h1>
    <p>Account and market values are retrieved from verified services, not preview estimates.</p>
    <div className="ui-skeleton-stack" aria-hidden="true"><span className="ui-skeleton ui-skeleton--short"/><span className="ui-skeleton"/></div>
  </main>;
}
