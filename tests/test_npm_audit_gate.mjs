import assert from "node:assert/strict";
import test from "node:test";
import { evaluateAuditReport } from "../scripts/npm_audit_gate.mjs";

const clean = () => ({ vulnerabilities: {}, metadata: { vulnerabilities: {
  info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0,
} } });

test("clean complete evidence passes", () => assert.equal(evaluateAuditReport(clean(), 0).passed, true));

test("failed or missing scans cannot pass", () => {
  for (const exit of [null, 2, 3, -1]) assert.throws(() => evaluateAuditReport(clean(), exit));
  for (const report of [{}, { error: { code: "ENOTFOUND" } }, { vulnerabilities: {} }]) {
    assert.throws(() => evaluateAuditReport(report, 1));
  }
});

test("previously excepted tooling advisories still block release", () => {
  const report = clean();
  report.metadata.vulnerabilities.high = 1;
  report.metadata.vulnerabilities.total = 1;
  report.vulnerabilities.braces = { severity: "high", via: [{ url: "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm" }] };
  const result = evaluateAuditReport(report, 1);
  assert.equal(result.passed, false);
  assert.equal(result.exceptionsApplied, false);
});

test("aggregate high count cannot be hidden by empty details", () => {
  const report = clean();
  report.metadata.vulnerabilities.high = 1;
  report.metadata.vulnerabilities.total = 1;
  assert.equal(evaluateAuditReport(report, 1).passed, false);
});

test("unknown row severity and invalid aggregate counts reject malformed evidence", () => {
  const report = clean();
  report.vulnerabilities.example = { severity: "unknown" };
  assert.throws(() => evaluateAuditReport(report, 0));
  const inconsistent = clean();
  inconsistent.metadata.vulnerabilities.total = 3;
  assert.throws(() => evaluateAuditReport(inconsistent, 0));
});
