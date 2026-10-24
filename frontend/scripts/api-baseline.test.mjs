import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../src/", import.meta.url));
function files(dir) {
  return readdirSync(dir).flatMap(name => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : /\.(tsx?|mjs)$/.test(name) ? [path] : [];
  });
}

test("redesigns never silently drop a backend capability the web app used", () => {
  const source = files(root).map(file => readFileSync(file, "utf8")).join("\n");
  const baseline = JSON.parse(readFileSync(new URL("./api-call-baseline.json", import.meta.url), "utf8"));
  const missing = baseline.calls.filter(({ method, path }) => !source.includes(`client.${method}("${path}"`));
  assert.deepEqual(missing, [], "Removed API usage must be an explicit, documented decision: update api-call-baseline.json with the rationale");
});

test("every page route that existed before the redesign still exists", () => {
  const routes = ["page.tsx", "[slug]/page.tsx", "login/page.tsx", "recover/page.tsx", "magic-login/page.tsx",
    "app/page.tsx", "app/[...slug]/page.tsx", "api/v1/platform/[[...path]]/route.ts", "retained-workspace/route.ts",
    "frontend-health/route.ts", "frontend_health/route.ts"];
  for (const route of routes) assert.ok(statSync(join(root, "app", route)).isFile(), route);
});
