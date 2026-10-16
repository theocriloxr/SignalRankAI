#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

export function evaluateAuditReport(report, exitCode) {
  if (![0, 1].includes(exitCode) || !report || report.error ||
      !report.vulnerabilities || typeof report.vulnerabilities !== "object" || Array.isArray(report.vulnerabilities)) {
    throw new Error("npm_audit_failed_or_missing_vulnerability_evidence");
  }
  const counts = report.metadata?.vulnerabilities;
  const severities = ["info", "low", "moderate", "high", "critical"];
  if (!counts || severities.some(level => !Number.isInteger(counts[level]) || counts[level] < 0) ||
      !Number.isInteger(counts.total) || counts.total !== severities.reduce((n, level) => n + counts[level], 0)) {
    throw new Error("npm_audit_invalid_vulnerability_counts");
  }
  const blocked = [];
  for (const [name, row] of Object.entries(report.vulnerabilities)) {
    if (!row || !severities.includes(row.severity)) throw new Error("npm_audit_invalid_vulnerability_row");
    if (["high", "critical"].includes(row.severity)) blocked.push({ name, severity: row.severity });
  }
  return { passed: counts.high === 0 && counts.critical === 0 && blocked.length === 0,
    vulnerabilityCounts: counts, blocked, exceptionsApplied: false };
}

function main() {
  const index = process.argv.indexOf("--project");
  const project = index >= 0 ? process.argv[index + 1] : "";
  if (!["frontend", "mobile"].includes(project)) {
    console.error("usage: npm_audit_gate.mjs --project frontend|mobile");
    return 2;
  }
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const audit = spawnSync(process.platform === "win32" ? "npm.cmd" : "npm", ["audit", "--json"], {
    cwd: path.join(root, project), encoding: "utf8", maxBuffer: 16 * 1024 * 1024,
    shell: process.platform === "win32",
  });
  try {
    if (audit.error) throw new Error("npm_audit_process_failed");
    const result = evaluateAuditReport(JSON.parse(audit.stdout || "{}"), audit.status);
    console.log(JSON.stringify({ project, auditExitCode: audit.status, ...result }, null, 2));
    return result.passed ? 0 : 1;
  } catch (error) {
    console.error(error.message);
    return 2;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exit(main());
