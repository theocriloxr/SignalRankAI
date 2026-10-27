export const dynamic = "force-dynamic";

/** UI process health only. Backend/broker readiness is never inferred here. */
export function GET() {
  const commit = process.env.SIGNALRANK_FRONTEND_COMMIT ?? "";
  const valid = /^[a-f0-9]{40}$/.test(commit);
  return Response.json({
    service: "signalrank-web", status: valid ? "ready" : "source_identity_unavailable",
    commit: valid ? commit : null, financial_readiness_certified: false,
  }, { status: valid ? 200 : 503, headers: { "Cache-Control": "no-store" } });
}
