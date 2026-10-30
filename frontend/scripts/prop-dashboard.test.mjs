import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const view = readFileSync(new URL("../src/components/PropDashboard.tsx", import.meta.url), "utf8");
const brokers = readFileSync(new URL("../src/components/BrokerAccounts.tsx", import.meta.url), "utf8");

test("the prop dashboard reads its own endpoint and only ever writes display-only objectives", () => {
  const calls = [...view.matchAll(/client\.(GET|PUT|POST|DELETE|PATCH)\("([^"]+)"/g)].map(m => `${m[1]} ${m[2]}`).sort();
  assert.deepEqual(calls, ["GET /api/v1/platform/broker/connections/{connection_id}/prop-dashboard",
    "PUT /api/v1/platform/broker/connections/{connection_id}/prop-objectives"]);
  assert.doesNotMatch(view, /\/execution|\/policy"|safety-freeze|localStorage|sessionStorage/);
  assert.match(view, /Display only: these never change what orders are allowed, your risk policy or its certification\./);
});

test("missing data reads as unavailable, never zero, and percentages are entered as percent", () => {
  assert.match(view, /return n === null \? "Unavailable"/);
  assert.match(view, /No broker equity snapshots yet/);
  assert.match(view, /Number\(form\.target\) \/ 100/);
});

test("the broker view shows the dashboard only when the account has a policy", () => {
  assert.match(brokers, /\{policy&&<PropDashboard key=\{selected\} connectionId=\{selected\}\/>\}/);
});
