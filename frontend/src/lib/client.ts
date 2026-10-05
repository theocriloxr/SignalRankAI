import createClient from "openapi-fetch";
import type { paths } from "./api";
import { platformFetch } from "./transport";

const configured = process.env.NEXT_PUBLIC_SIGNALRANK_API_BASE_URL?.trim();
const baseUrl = configured ? configured.replace(/\/$/, "") : "";

const client = createClient<paths>({
  baseUrl,
  credentials: "include",
  fetch: platformFetch,
  headers: { "X-SignalRank-Client": "web-next" },
});

export default client;
