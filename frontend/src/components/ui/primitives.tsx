import type { ReactNode } from "react";
import type { IconName } from "./Icon";

/** Presentational primitives shared by public, account and workspace surfaces.
 * They never fetch data, so they are safe in server and client components alike. */

export type Tone = "neutral" | "brand" | "positive" | "negative" | "warning" | "info";

export function Card({ title, eyebrow, description, actions, children, className, tone, id, as = "section", labelledBy }: {
  title?: ReactNode; eyebrow?: ReactNode; description?: ReactNode; actions?: ReactNode;
  children?: ReactNode; className?: string; tone?: "muted" | "danger"; id?: string;
  as?: "section" | "article" | "div"; labelledBy?: string;
}) {
  const Tag = as;
  const headingId = labelledBy ?? (id ? `${id}-title` : undefined);
  return <Tag id={id} aria-labelledby={title && headingId ? headingId : undefined}
    className={["ui-card", tone ? `ui-card--${tone}` : "", className ?? ""].filter(Boolean).join(" ")}>
    {(title || eyebrow || actions) && <header className="ui-card-head">
      <div>
        {eyebrow && <p className="ui-eyebrow">{eyebrow}</p>}
        {title && <h2 className="ui-card-title" id={headingId}>{title}</h2>}
        {description && <p className="ui-card-desc">{description}</p>}
      </div>
      {actions && <div className="ui-actions">{actions}</div>}
    </header>}
    {children}
  </Tag>;
}

export function Badge({ tone = "neutral", children, plain = false }: { tone?: Tone; children: ReactNode; plain?: boolean }) {
  return <span className={`ui-badge${tone === "neutral" ? "" : ` ui-badge--${tone}`}${plain ? " ui-badge--plain" : ""}`}>{children}</span>;
}

/** Context notice for honest scope statements: simulated vs live, receipts vs fills.
 * A tinted rule on the left carries the tone; no icon. */
export function Notice({ tone = "info", children, role }: { tone?: "info" | "warning" | "danger" | "success" | "neutral"; children: ReactNode; role?: "status" | "alert" }) {
  return <div className={`ui-notice ui-notice--${tone}`} role={role}>
    <div>{children}</div>
  </div>;
}

/** ``icon`` is accepted for older call sites and ignored: figures read better without one. */
export function Stat({ label, value, detail }: { label: string; value: string; detail?: string; icon?: IconName }) {
  return <div className="ui-stat">
    <span className="ui-stat-label">{label}</span>
    <strong className="ui-stat-value" data-unavailable={value === "Unavailable" ? "true" : undefined}>{value}</strong>
    {detail && <small className="ui-stat-detail">{detail}</small>}
  </div>;
}

export function KV({ label, value }: { label: string; value: ReactNode }) {
  return <div className="ui-kv-row"><dt>{label}</dt><dd>{value}</dd></div>;
}

export function KVList({ children, grid = false }: { children: ReactNode; grid?: boolean }) {
  return <dl className={grid ? "ui-kv ui-kv--grid" : "ui-kv"}>{children}</dl>;
}

/** ``icon`` is accepted for older call sites and ignored. */
export function Empty({ title, children }: { title: string; children?: ReactNode; icon?: IconName }) {
  return <div className="ui-empty">
    <strong>{title}</strong>
    {children && <p>{children}</p>}
  </div>;
}

export function Loading({ children }: { children: ReactNode }) {
  return <div className="ui-loading" role="status" aria-live="polite"><span className="ui-spinner" aria-hidden="true" />{children}</div>;
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return <div className="ui-skeleton-stack" aria-hidden="true">
    {Array.from({ length: rows }, (_, i) => <span key={i} className={i === 0 ? "ui-skeleton ui-skeleton--short" : "ui-skeleton"} />)}
  </div>;
}

export function Feedback({ error = false, children }: { error?: boolean; children: ReactNode }) {
  return <p className={error ? "ui-feedback ui-feedback--error" : "ui-feedback"} role={error ? "alert" : "status"}>{children}</p>;
}

/** ``compact`` drops the minimum width and lets cells wrap, for narrow two- or three-column tables. */
export function TableWrap({ label, children, id, compact = false }: { label: string; children: ReactNode; id?: string; compact?: boolean }) {
  return <div className="ui-table-wrap" tabIndex={0} role="region" aria-label={label} id={id}>
    <table className={compact ? "ui-table ui-table--compact" : "ui-table"}>{children}</table>
  </div>;
}

/** Direction as a coloured word: never infer direction; unknown stays neutral. */
export function DirectionBadge({ direction }: { direction: string }) {
  const value = direction.trim().toUpperCase();
  const tone: Tone = value === "LONG" || value === "BUY" ? "positive" : value === "SHORT" || value === "SELL" ? "negative" : "neutral";
  const word = value ? value[0] + value.slice(1).toLowerCase() : "Direction not set";
  return <span className={`ui-direction ui-direction--${tone}`}>{word}</span>;
}
