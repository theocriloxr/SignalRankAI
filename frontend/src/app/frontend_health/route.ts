// Railway's healthcheck configuration accepts underscores, but rejects hyphens.
// Keep both URLs on the same source-identity check.
export const dynamic = "force-dynamic";
export { GET } from "../frontend-health/route";
