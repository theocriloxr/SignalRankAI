import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const owner = readFileSync(new URL("../src/components/OwnerControls.tsx", import.meta.url), "utf8");
const workspace = readFileSync(new URL("../src/components/WorkspaceLive.tsx", import.meta.url), "utf8");

test("owner controls only reach the scoped switch, merge review and AI spend endpoints", () => {
  const calls = [...owner.matchAll(/client\.(GET|POST)\("([^"]+)"/g)].map(([, method, path]) => `${method} ${path}`);
  assert.deepEqual([...new Set(calls)].sort(), [
    "GET /api/v1/platform/operator/account-merges",
    "GET /api/v1/platform/operator/account-merges/{merge_id}",
    "GET /api/v1/platform/operator/ai-spend",
    "POST /api/v1/platform/operator/account-merges/{merge_id}/apply",
    "POST /api/v1/platform/operator/kill-switch/scoped",
  ]);
  assert.doesNotMatch(owner, /\/operator\/kill-switch"|live_financial|real_execution|auto_execution|payout|\/broker\//);
});

test("every change needs an explicit confirmation", () => {
  assert.match(owner, /phrase !== "ENGAGE"/);
  assert.match(owner, /Confirm release/);
  assert.match(owner, /!checked \|\| typed\.trim\(\) !== selected/);
  assert.match(owner, /confirm_merge_id: typed\.trim\(\)/);
  assert.match(owner, /disabled=\{saving \|\| failed\}/);
});

test("a stale sign-in is explained, and admins can look but not change", () => {
  assert.match(owner, /recent authentication/i);
  assert.match(owner, /needs a fresh sign-in/);
  assert.match(owner, /Only the owner account can view and change scoped kill switches/);
  assert.match(owner, /only the owner can complete one/);
  assert.match(workspace, /<OwnerControls authority=\{display\(state\.data\.authority,""\)\}\/>/);
});

test("owner screens keep no state in browser storage", () => {
  assert.doesNotMatch(owner, /localStorage|sessionStorage|indexedDB|document\.cookie|console\.(log|info|debug)/);
});
