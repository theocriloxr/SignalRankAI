import { observeService } from "../lib/public-status";

const labels = {available:"Available", degraded:"Degraded", unavailable:"Could not verify", unconfigured:"Status feed not configured"};

/** Point-in-time public observation. Never publishes diagnostics or implies trading readiness. */
export async function PublicStatus() {
  const [process, dependencies] = await Promise.all([observeService("/healthz"),observeService("/readyz")]);
  return <section className="ui-card mk-observations" aria-labelledby="service-status-title">
    <div className="ui-card-head"><div>
      <p className="ui-eyebrow">Current service observation</p>
      <h2 className="ui-card-title" id="service-status-title">Live connection check</h2>
      <p className="ui-card-desc">These checks report API availability and service dependencies when this page loads. They do not certify signal quality, broker execution or trading eligibility.</p>
    </div></div>
    <dl>{[{name:"Account API",value:process},{name:"Backend dependencies",value:dependencies}].map(({name,value}) =>
      <div key={name}><dt>{name}</dt><dd data-state={value.state}>{labels[value.state]}</dd></div>)}</dl>
    <p className="ui-muted">Observed <time dateTime={process.observedAt}>{new Date(process.observedAt).toUTCString()}</time>. Reload for a fresh observation.</p>
  </section>;
}
