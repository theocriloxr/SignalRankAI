import { proxyPlatformRequest } from "../../../../../lib/platform-proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
function forward(request: Request) { return proxyPlatformRequest(request); }
export const GET = forward;
export const HEAD = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
export const OPTIONS = forward;
