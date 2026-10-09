/**
 * Trustworthy financial labels shared by native account surfaces.
 * Never coerce unavailable values into zero or invent a currency.
 */
export function finiteNumber(value: unknown): number | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}

export function quantityLabel(value: unknown, places = 2): string {
  const amount = finiteNumber(value);
  if (amount === null) return "Unavailable";
  return new Intl.NumberFormat("en-NG", { maximumFractionDigits: places }).format(amount);
}

export function currencyLabel(value: unknown, code: unknown): string {
  const amount = finiteNumber(value);
  const currency = typeof code === "string" ? code.trim().toUpperCase() : "";
  if (amount === null || !/^[A-Z]{3}$/.test(currency)) return "Unavailable";
  try {
    return new Intl.NumberFormat("en-NG", {
      style: "currency",
      currency,
      currencyDisplay: "code",
    }).format(amount);
  } catch {
    return "Unavailable";
  }
}

/** Backend calibrated win rates are fractional, 0–1. */
export function percentLabel(value: unknown): string {
  const v = finiteNumber(value);
  if (v === null || v < 0 || v > 1) return "Unavailable";
  return (v * 100).toFixed(1) + "%";
}

export function safeLabel(value: unknown, fallback = "Unavailable"): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

export function amountTone(value: unknown): "positive" | "negative" | "neutral" {
  const number = finiteNumber(value);
  return number === null || number === 0 ? "neutral" : number > 0 ? "positive" : "negative";
}
