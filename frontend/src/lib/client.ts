import createClient from "openapi-fetch";
import type { paths } from "./api";

const configured = process.env.NEXT_PUBLIC_SIGNALRANK_API_BASE_URL?.trim();
const baseUrl = configured ? configured.replace(/\/$/, "") : "";

const client = createClient<paths>({
  baseUrl,
  headers: { "X-SignalRank-Client": "web-next" },
});

export default client;
