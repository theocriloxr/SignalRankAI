import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  record, rows, display, finite, numberLabel, probabilityLabel,
  moneyLabel, timeLabel, brokerMode, statusText,
} from "../src/lib/presentation.ts";

test("unavailable money and market values never turn into fabricated zeros", () => {
  for (const input of [null, undefined, "", "NaN", "Infinity", {}, []]) {
    assert.equal(finite(input), null);
    assert.equal(numberLabel(input), "Unavailable");
    assert.equal(moneyLabel(input, "USD"), "Unavailable");
  }
  assert.equal(moneyLabel(200, null), "Unavailable");
  assert.equal(moneyLabel(200, "NOT-A-CURRENCY"), "Unavailable");
  assert.match(moneyLabel(125.5, "USD"), /USD/);
  assert.match(moneyLabel("100", "NGN"), /NGN/);
  assert.equal(numberLabel(0), "0");
});

test("probabilities are normalized fractions and invalid values stay unavailable", () => {
  assert.equal(probabilityLabel(0.625), "62.5%");
  assert.equal(probabilityLabel("0.93"), "93.0%");
  assert.equal(probabilityLabel(0), "0.0%");
  for (const value of [null, "", 1.7, -0.2, "unknown", 85]) {
    assert.equal(probabilityLabel(value), "Unavailable");
  }
});

test("broker connection environment is never inferred from account labels", () => {
  assert.equal(brokerMode({ account_label:"Demo trading", environment:"unknown" }), "Environment unverified");
  assert.equal(brokerMode({ environment:"demo" }), "DEMO");
  assert.equal(brokerMode({ environment:"live" }), "LIVE — certification required");
  assert.equal(brokerMode({}), "Environment unverified");
});

test("lists and identity fields are narrowed without serializing private objects", () => {
  assert.deepEqual(rows([{asset:"BTC"},{asset:"ETH"},null, 0, "oops"]),[{asset:"BTC"},{asset:"ETH"}]);
  assert.deepEqual(record(null), {});
  assert.equal(display({secret:"test"}), "Unavailable");
  assert.equal(display(" XAUUSD "), "XAUUSD");
  assert.equal(timeLabel("not-a-date"), "Unavailable");
});

test("denied, expired and unavailable API responses are separate states", () => {
  assert.match(statusText(401), /expired|not signed in/i);
  assert.match(statusText(403), /permission/i);
  assert.match(statusText(429), /rate-limited/i);
  assert.match(statusText(503), /unavailable/i);
});

test("workspace never calls an order or high-risk mutation from a read-only view", () => {
  const src = readFileSync(new URL("../src/components/WorkspaceLive.tsx", import.meta.url), "utf8");
  assert.match(src, /api\/v1\/platform\/me/);
  assert.ok(src.includes('client.GET("/api/v1/platform/signals"'));
  assert.doesNotMatch(src, /client\.(POST|PUT|DELETE|PATCH)\(/);
  assert.doesNotMatch(src, /localStorage|sessionStorage/);
});


test("safe account form actions are limited to owned watchlists support and journal", () => {
  const source=readFileSync(new URL("../src/components/AccountCreation.tsx", import.meta.url),"utf8");
  const targets=[...source.matchAll(/client\.POST\("([^"]+)"/g)].map(match=>match[1]).sort();
  assert.deepEqual(targets, [
    "/api/v1/platform/journal",
    "/api/v1/platform/support/tickets",
    "/api/v1/platform/watchlists",
  ]);
  assert.doesNotMatch(source,/\/broker\/|\/execute|kill-switch|\/billing\/checkout|localStorage|sessionStorage/);
});

test("one-time email links only consume tokens after explicit confirmation", () => {
  const source=readFileSync(new URL("../src/components/AccountEmailLink.tsx", import.meta.url),"utf8");
  assert.match(source,/onClick=\{consume\}/);
  assert.match(source,/onSubmit=\{verifyMfa\}/);
  assert.ok(source.includes('client.POST("/api/v1/platform/auth/email-verification/complete"'));
  assert.ok(source.includes('client.POST("/api/v1/platform/auth/magic-link/complete"'));
  assert.ok(source.includes('client.POST("/api/v1/platform/auth/mfa/complete"'));
  assert.doesNotMatch(source,/localStorage|sessionStorage/);
});
