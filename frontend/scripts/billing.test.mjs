import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { paystackCheckoutUrl, returnedReference } from "../src/lib/billing.ts";

test("checkout redirects only to Paystack-hosted HTTPS pages", () => {
  assert.equal(paystackCheckoutUrl("https://checkout.paystack.com/abc123"), "https://checkout.paystack.com/abc123");
  assert.equal(paystackCheckoutUrl("https://paystack.com/pay/x"), "https://paystack.com/pay/x");
  for (const bad of ["http://checkout.paystack.com/abc", "https://checkout.paystack.com.evil.test/abc",
    "https://evilpaystack.com/abc", "https://user:pw@checkout.paystack.com/abc", "https://checkout.paystack.com:8443/abc",
    "javascript:alert(1)", "//checkout.paystack.com/abc", "", null, 42, {}]) {
    assert.equal(paystackCheckoutUrl(bad), null, String(bad));
  }
});

test("payment return reference is shape-validated and never trusted for amount or tier", () => {
  assert.equal(returnedReference("?trxref=abc_123&reference=abc_123"), "abc_123");
  assert.equal(returnedReference("trxref=T-9.8:7"), "T-9.8:7");
  for (const bad of ["", "?reference=", "?reference=a", "?reference=<script>", "?reference=" + "x".repeat(161), "?reference=a%20b"]) {
    assert.equal(returnedReference(bad), null, bad);
  }
});

test("billing UI uses server-priced checkout, explicit recurring consent and explicit confirmation", () => {
  const src = readFileSync(new URL("../src/components/BillingCenter.tsx", import.meta.url), "utf8");
  assert.ok(src.includes('client.GET("/api/v1/platform/billing/products"'));
  assert.ok(src.includes('client.POST("/api/v1/platform/billing/checkout"'));
  assert.ok(src.includes('client.POST("/api/v1/platform/billing/confirm"'));
  assert.ok(src.includes('client.POST("/api/v1/platform/billing/cancel-auto-renew"'));
  assert.ok(src.includes('client.POST("/api/v1/platform/billing/refund-request"'));
  // The browser never sends an amount, tier or duration: the server prices the product.
  assert.doesNotMatch(src, /body:\s*\{[^}]*\b(amount|price|tier|duration_days)\s*:/);
  assert.ok(src.includes("recurring_acknowledged: recurring && acknowledged[id] === true"));
  assert.ok(src.includes("paystackCheckoutUrl(record(r.data).authorization_url)"));
  // Confirmation and cancellation only happen on an explicit click.
  assert.match(src, /onClick=\{confirm\}/);
  assert.match(src, /if \(busy \|\| !confirming\) return/);
  assert.ok(src.includes("body: { confirm: true }"));
  assert.doesNotMatch(src, /localStorage|sessionStorage|\/broker\/|\/execute|kill.switch/);
});
