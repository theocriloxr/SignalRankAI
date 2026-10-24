import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = name => readFileSync(new URL(`../src/components/${name}`, import.meta.url), "utf8");
const developer = read("DeveloperAccess.tsx");
const plan = read("PlanAndReferrals.tsx");
const workspace = read("WorkspaceLive.tsx");
const privacy = read("PrivacyCenter.tsx");

test("one-time credentials live only in component memory", () => {
  for (const source of [developer, plan]) {
    assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB|document\.cookie/);
    assert.doesNotMatch(source, /console\.(log|info|debug)/);
  }
  assert.match(developer, /setSecret\(\{label:`API key/);
  assert.match(developer, /setSecret\(\{label:`Signing secret/);
  assert.match(developer, /shown once/);
});

test("revoking a key or webhook needs a second, explicit confirmation", () => {
  assert.match(developer, /if\(busy\|\|confirm!=="key:"\+id\)return;/);
  assert.match(developer, /if\(busy\|\|confirm!=="hook:"\+id\)return;/);
  assert.match(developer, /Confirm revoke/);
});

test("developer credentials stay read-only and cannot reach trading paths", () => {
  assert.doesNotMatch(developer, /webhooks:write|execution|place.order|\/broker\//);
  for (const scope of ["signals:read", "instruments:read", "portfolio:read", "paper:read", "journal:read", "organization:read"]) {
    assert.ok(developer.includes(`"${scope}"`), scope);
  }
  assert.match(developer, /protocol!=="https:"/, "webhook endpoints are checked for https before the server SSRF guard");
});

test("plan and referral panel is display-only and never promises cash", () => {
  assert.doesNotMatch(plan, /client\.(POST|PUT|PATCH|DELETE)/);
  assert.match(plan, /never cash/);
  assert.match(plan, /startsWith\("https:\/\/t\.me\/"\)/);
});

test("both panels are reachable from account settings", () => {
  assert.match(workspace, /<PlanAndReferrals\/><DeveloperAccess\/><PrivacyCenter onChanged=\{refresh\}\/>/);
  assert.doesNotMatch(workspace, /client\.(POST|PUT|PATCH|DELETE)/);
});

test("privacy panel exports in memory and only requests a reviewed deletion", () => {
  assert.doesNotMatch(privacy, /localStorage|sessionStorage|indexedDB|document\.cookie/);
  assert.match(privacy, /URL\.revokeObjectURL/);
  assert.match(privacy, /disabled=\{busy\|\|phrase\.trim\(\)!==PHRASE\}/);
  assert.doesNotMatch(privacy, /client\.DELETE/);
  assert.match(privacy, /opens a support review rather than deleting immediately/);
});
