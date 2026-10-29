import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import test from "node:test";
import { proxyPlatformRequest } from "../src/lib/platform-proxy.ts";

const SECRET = "s".repeat(40);

async function forwarded(headers, secret) {
  const oldOrigin = process.env.SIGNALRANK_PLATFORM_API_ORIGIN, oldSecret = process.env.SIGNALRANK_CLIENT_IP_SECRET;
  process.env.SIGNALRANK_PLATFORM_API_ORIGIN = "https://backend.example.test";
  if (secret === undefined) delete process.env.SIGNALRANK_CLIENT_IP_SECRET; else process.env.SIGNALRANK_CLIENT_IP_SECRET = secret;
  try {
    let sent;
    await proxyPlatformRequest(new Request("https://web.example.test/api/v1/platform/me", { headers }),
      async (_url, options) => { sent = options.headers; return new Response("{}", { status: 200 }); });
    return sent;
  } finally {
    if (oldOrigin === undefined) delete process.env.SIGNALRANK_PLATFORM_API_ORIGIN; else process.env.SIGNALRANK_PLATFORM_API_ORIGIN = oldOrigin;
    if (oldSecret === undefined) delete process.env.SIGNALRANK_CLIENT_IP_SECRET; else process.env.SIGNALRANK_CLIENT_IP_SECRET = oldSecret;
  }
}

test("browser-chosen forwarding headers never reach the backend", async () => {
  const sent = await forwarded({ "X-Forwarded-For": "1.2.3.4", "X-Real-IP": "203.0.113.7",
    "X-SignalRank-Client-IP": "9.9.9.9", "X-SignalRank-Client-IP-Signature": "forged" });
  assert.equal(sent.get("x-forwarded-for"), null);
  assert.equal(sent.get("x-real-ip"), "203.0.113.7"); // the edge-set value in front of this server
  assert.equal(sent.get("x-signalrank-client-ip"), null);
  assert.equal(sent.get("x-signalrank-client-ip-signature"), null);
});

test("a malformed address is dropped", async () => {
  const sent = await forwarded({ "X-Real-IP": "203.0.113.7, 10.0.0.1" });
  assert.equal(sent.get("x-real-ip"), null);
});

test("with the shared secret the address is signed in the backend's format", async () => {
  const sent = await forwarded({ "X-Real-IP": "2001:db8::7" }, SECRET);
  const ip = sent.get("x-signalrank-client-ip"), ts = sent.get("x-signalrank-client-ip-ts");
  assert.equal(ip, "2001:db8::7");
  assert.ok(Math.abs(Number(ts) - Date.now() / 1000) < 5);
  assert.equal(sent.get("x-signalrank-client-ip-signature"), createHmac("sha256", SECRET).update(`${ip}.${ts}`).digest("hex"));
  // Same vector as tests/test_client_ip_trust_20261029.py computes with core/client_ip.py.
  assert.equal(createHmac("sha256", SECRET).update("203.0.113.7.1800000000").digest("hex"),
    "6b807005bcbcb7ab21745b78432f2679c2c437e6531047aa4086872de563f977");
});

test("a short secret is never used", async () => {
  const sent = await forwarded({ "X-Real-IP": "203.0.113.7" }, "too-short");
  assert.equal(sent.get("x-signalrank-client-ip-signature"), null);
});
