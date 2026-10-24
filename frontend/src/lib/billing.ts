/** Paystack checkout must only ever leave for a Paystack-hosted HTTPS page. */
export function paystackCheckoutUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 2048) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== "https:" || url.username || url.password || url.port) return null;
    if (host !== "paystack.com" && !host.endsWith(".paystack.com")) return null;
    return url.href;
  } catch { return null; }
}

/** Paystack appends ?reference=…&trxref=… to its return URL. Validate the shape only;
 * the server verifies the transaction with Paystack and checks it belongs to this account. */
export function returnedReference(search: string): string | null {
  const params = new URLSearchParams(search);
  const value = (params.get("reference") || params.get("trxref") || "").trim();
  return /^[A-Za-z0-9._:-]{3,160}$/.test(value) ? value : null;
}
