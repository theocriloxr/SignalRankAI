#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const projectIndex = process.argv.indexOf("--project");
const project = projectIndex >= 0 ? process.argv[projectIndex + 1] : "";
if (!["frontend", "mobile"].includes(project)) {
  console.error("usage: npm_audit_gate.mjs --project frontend|mobile");
  process.exit(2);
}

const root = process.cwd();
const projectDir = path.join(root, project);
const lockPath = path.join(projectDir, "package-lock.json");
const sourceDir = path.join(projectDir, "src");
const lockText = fs.readFileSync(lockPath, "utf8");
const lock = JSON.parse(lockText);
const packages = lock.packages || {};

const audit = spawnSync("npm", ["audit", "--json"], {
  cwd: projectDir,
  encoding: "utf8",
  maxBuffer: 16 * 1024 * 1024,
});
let report;
try {
  report = JSON.parse(audit.stdout || "{}");
} catch {
  console.error("npm audit did not return valid JSON");
  console.error((audit.stdout || "").slice(0, 4000));
  console.error((audit.stderr || "").slice(0, 4000));
  process.exit(2);
}
const vulnerabilities = report.vulnerabilities || {};
const rank = { info: 0, low: 1, moderate: 2, high: 3, critical: 4 };

function advisoryIds(name, seen = new Set()) {
  if (seen.has(name)) return new Set();
  seen.add(name);
  const row = vulnerabilities[name];
  if (!row) return new Set();
  const result = new Set();
  for (const via of row.via || []) {
    if (typeof via === "string") {
      for (const id of advisoryIds(via, new Set(seen))) result.add(id);
    } else {
      const url = String(via.url || "");
      const match = url.match(/GHSA-[A-Za-z0-9-]+/i);
      result.add(match ? match[0].toUpperCase() : "UNIDENTIFIED");
    }
  }
  return result;
}

function sourceContains(tokens) {
  if (!fs.existsSync(sourceDir)) return [];
  const hits = [];
  const stack = [sourceDir];
  while (stack.length) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
      } else if (/\.(js|jsx|ts|tsx|mjs|cjs)$/.test(entry.name)) {
        const body = fs.readFileSync(full, "utf8");
        for (const token of tokens) {
          if (body.includes(token)) hits.push(path.relative(root, full) + ":" + token);
        }
      }
    }
  }
  return hits;
}

const failures = [];
const excepted = [];
const expiry = "2026-10-17";
if (new Date().toISOString().slice(0, 10) > expiry) {
  failures.push("security exception expired on " + expiry);
}

const allowed = project === "frontend"
  ? new Set(["GHSA-VFJ7-8CJW-P6XM"])
  : new Set(["GHSA-VFJ7-8CJW-P6XM", "GHSA-86W9-CPQP-85RV"]);

if (project === "frontend") {
  const braces = packages["node_modules/braces"] || {};
  if (braces.version !== "3.0.3" || braces.dev !== true) {
    failures.push("frontend braces must remain version 3.0.3 and dev-only");
  }
  for (const marker of [
    '"node_modules/eslint-config-next"',
    '"node_modules/@next/eslint-plugin-next"',
    '"node_modules/fast-glob"',
    '"node_modules/micromatch"',
  ]) {
    if (!lockText.includes(marker)) failures.push("missing expected frontend tooling path " + marker);
  }
  const hits = sourceContains(["braces", "micromatch"]);
  if (hits.length) failures.push("frontend app source imports exception tooling: " + hits.join(","));
} else {
  const braces = packages["node_modules/braces"] || {};
  const forge = packages["node_modules/node-forge"] || {};
  if (braces.version !== "3.0.3") failures.push("mobile braces version changed");
  if (forge.version !== "1.4.0") failures.push("mobile node-forge version changed");
  for (const marker of [
    '"node_modules/metro-file-map"',
    '"node_modules/@expo/metro-file-map"',
    '"node_modules/@expo/code-signing-certificates"',
    '"node_modules/expo/node_modules/@expo/cli"',
  ]) {
    if (!lockText.includes(marker)) failures.push("missing expected mobile build-tool path " + marker);
  }
  const hits = sourceContains(["braces", "micromatch", "node-forge", "@expo/code-signing-certificates"]);
  if (hits.length) failures.push("mobile app source imports exception tooling: " + hits.join(","));
}

for (const [name, row] of Object.entries(vulnerabilities)) {
  const severity = String(row.severity || "unknown").toLowerCase();
  if ((rank[severity] ?? 99) < rank.high) continue;
  const ids = advisoryIds(name);
  const unknown = [...ids].filter((id) => !allowed.has(id));
  if (!ids.size || unknown.length) {
    failures.push("unapproved " + severity + " vulnerability " + name + " advisories=" + JSON.stringify([...ids]));
  } else {
    excepted.push({ name, severity, advisories: [...ids] });
  }
}

console.log(JSON.stringify({
  project,
  auditExitCode: audit.status,
  vulnerabilityCounts: report.metadata?.vulnerabilities || {},
  excepted,
  exceptionExpires: expiry,
  failures,
}, null, 2));

process.exit(failures.length ? 1 : 0);
