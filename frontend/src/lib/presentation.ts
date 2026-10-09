/** Read-only presentation helpers. Missing market/financial data never becomes a fabricated zero. */
export type Row = Record<string, unknown>;

export function record(value: unknown): Row {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
}

export function rows(value: unknown): Row[] {
  return Array.isArray(value) ? value.filter((item): item is Row =>
    item !== null && typeof item === "object" && !Array.isArray(item)) : [];
}

export function display(value: unknown, fallback = "Unavailable"): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

export function finite(value: unknown): number | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function numberLabel(value: unknown, fractionDigits = 2): string {
  const n = finite(value);
  return n === null ? "Unavailable" : new Intl.NumberFormat("en-NG", {
    maximumFractionDigits: fractionDigits,
  }).format(n);
}

/** The backend's ml_probability_calibrated is a [0, 1] probability, not a percentage. */
export function probabilityLabel(value: unknown): string {
  const n = finite(value);
  if (n === null || n < 0 || n > 1) return "Unavailable";
  return (n * 100).toFixed(1) + "%";
}

export function moneyLabel(value: unknown, currency: unknown): string {
  const amount = finite(value);
  const code = typeof currency === "string" ? currency.trim().toUpperCase() : "";
  if (amount === null || !/^[A-Z]{3}$/.test(code)) return "Unavailable";
  try {
    return new Intl.NumberFormat("en-NG", { style: "currency", currency: code, currencyDisplay: "code" }).format(amount);
  } catch { return "Unavailable"; }
}

export function timeLabel(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "Unavailable";
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return "Unavailable";
  return new Intl.DateTimeFormat("en-NG", { dateStyle: "medium", timeStyle: "short" }).format(time);
}

/** Public text is never allowed to infer that a broker account is live or demo. */
export function brokerMode(row: Row): string {
  if (row.environment === "demo") return "DEMO";
  if (row.environment === "live") return "LIVE — certification required";
  return "Environment unverified";
}

export function statusText(status: number | undefined): string {
  if (status === 401) return "Your session has expired or is not signed in.";
  if (status === 403) return "Your account does not have permission for this information.";
  if (status === 429) return "The service is temporarily rate-limited. Retry later.";
  return "The canonical data service is unavailable. No market or account value has been assumed.";
}
