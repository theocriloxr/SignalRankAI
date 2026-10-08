import createClient from "openapi-fetch";
import type { paths } from "./api";
import { platformFetch } from "./transport";

// Always use same-origin API paths so the readable sr_csrf cookie and
// HttpOnly session cookies have the same origin as the browser workspace.
// Next rewrites forward these paths to the configured, trusted server API.
const baseUrl = "";

const client = createClient<paths>({
  baseUrl,
  credentials: "include",
  fetch: platformFetch,
  headers: { "X-SignalRank-Client": "web-next" },
});

export default client;
