import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { Linter } from "eslint";
import nextPlugin from "@next/eslint-plugin-next";

const require = createRequire(import.meta.url);
const pluginRequire = createRequire(require.resolve("@next/eslint-plugin-next"));
const { getRootDirs } = pluginRequire("./utils/get-root-dirs.js");

function fixture(run) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "signalrank-lint-contract-"));
  try {
    for (const app of ["customer", "owner"]) {
      fs.mkdirSync(path.join(root, "apps", app, "pages"), { recursive: true });
      fs.writeFileSync(path.join(root, "apps", app, "pages", "dashboard.jsx"), "export default function Dashboard() { return null; }");
    }
    fs.writeFileSync(path.join(root, "apps", "readme.md"), "not an application directory");
    run(root.replaceAll("\\", "/"));
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("Next root discovery keeps directory, brace, array and Windows path behavior", () => fixture(root => {
  const discover = rootDir => getRootDirs({ cwd: root, settings: { next: { rootDir } } }).map(dir => path.resolve(dir).replaceAll("\\", "/")).sort();
  const expected = [`${root}/apps/customer`, `${root}/apps/owner`];
  assert.deepEqual(discover(`${root}/apps/*`), expected);
  assert.deepEqual(discover(`${root}/apps/{customer,owner}`), expected);
  assert.deepEqual(discover([`${root}/apps/customer`, `${root}/apps/owner`]), expected);
  assert.deepEqual(discover(`${root}/apps/*`.replaceAll("/", "\\")), expected);
  assert.deepEqual(discover(`${root}/missing/*`), []);
  assert.deepEqual(getRootDirs({ cwd: root, settings: {} }), [root]);
}));

test("the installed Next lint rule still detects navigation violations with glob roots", () => fixture(root => {
  const linter = new Linter({ cwd: root });
  const config = [{
    files: ["**/*.jsx"],
    languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { "@next/next": nextPlugin },
    settings: { next: { rootDir: `${root}/apps/*` } },
    rules: { "@next/next/no-html-link-for-pages": "error" },
  }];
  const source = href => `export default function Page() { return <a href="${href}">Dashboard</a>; }`;
  const messages = linter.verify(source("/dashboard"), config, "component.jsx");
  assert.equal(messages.length, 1);
  assert.equal(messages[0].ruleId, "@next/next/no-html-link-for-pages");
  assert.deepEqual(linter.verify(source("https://example.com/dashboard"), config, "component.jsx"), []);
}));

test("deeply nested root patterns cannot exhaust the lint process stack", () => fixture(root => {
  const script = `const {getRootDirs}=require(${JSON.stringify(pluginRequire.resolve("./utils/get-root-dirs.js"))});
    const assert=require('node:assert/strict');
    for (const depth of [65, 12000]) {
      assert.throws(() => getRootDirs({cwd:${JSON.stringify(root)},settings:{next:{rootDir:'{'.repeat(depth)+'a'+'}'.repeat(depth)}}}), /pattern/);
    }`;
  const result = spawnSync(process.execPath, ["--max-old-space-size=128", "-e", script], { cwd: root, encoding: "utf8", timeout: 5000 });
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stderr);
}));
