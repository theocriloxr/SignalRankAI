import { canonicalApiOrigin } from "./server-origin.ts";

export type ServiceObservation = {state:"available"|"degraded"|"unavailable"|"unconfigured"; observedAt:string};

/** Sanitized, uncached observation; never publish diagnostic payloads or infer broker eligibility. */
export async function observeService(path: "/healthz"|"/readyz", request: typeof fetch = fetch): Promise<ServiceObservation> {
  const observedAt = new Date().toISOString();
  let origin: string | null;
  try { origin = canonicalApiOrigin(); } catch { return {state:"unconfigured",observedAt}; }
  if (!origin) return {state:"unconfigured",observedAt};
  try {
    const response = await request(origin+path, {cache:"no-store",redirect:"error",signal:AbortSignal.timeout(4000),
      headers:{Accept:"application/json"}});
    if (!response.ok) return {state:response.status === 503 ? "degraded" : "unavailable",observedAt};
    const body: unknown = await response.json();
    if (!body || typeof body !== "object" || !("status" in body) || typeof body.status !== "string") {
      return {state:"unavailable",observedAt};
    }
    const healthy = ["healthy","ready","ok"].includes(body.status.toLowerCase()) &&
      (!("ready" in body) || body.ready === true);
    const checks = "checks" in body ? body.checks : undefined;
    // Web-only readiness uses booleans; the production frontdoor uses {ok,...}
    // records. Require explicit success in either schema and discard diagnostics.
    const checksPass = (checks === undefined && path === "/healthz") ||
      (checks !== null && typeof checks === "object" && !Array.isArray(checks) &&
      Object.keys(checks).length > 0 && Object.values(checks).every(value => value === true ||
        (value !== null && typeof value === "object" && !Array.isArray(value) &&
          "ok" in value && value.ok === true)));
    return {state:healthy && checksPass ? "available" : "degraded",observedAt};
  } catch { return {state:"unavailable",observedAt}; }
}
