import { observeService } from "../lib/public-status";

const labels = {available:"Available", degraded:"Degraded", unavailable:"Could not verify", unconfigured:"Status feed not configured"};

export async function PublicStatus() {
  const [process, dependencies] = await Promise.all([observeService("/healthz"),observeService("/readyz")]);
  return <section className="sr-public-observations" aria-labelledby="service-status-title">
    <div><p className="sr-overline">Current service observation</p><h2 id="service-status-title">Check the connection.</h2>
      <p>These checks report API availability and service dependencies at the time this page loads. They do not certify signal quality, broker execution or trading eligibility.</p></div>
    <dl>{[{name:"Account API",value:process},{name:"Backend dependencies",value:dependencies}].map(({name,value}) =>
      <div key={name}><dt>{name}</dt><dd data-state={value.state}>{labels[value.state]}</dd></div>)}</dl>
    <p>Observed <time dateTime={process.observedAt}>{new Date(process.observedAt).toUTCString()}</time>. Reload for a fresh observation.</p>
  </section>;
}
