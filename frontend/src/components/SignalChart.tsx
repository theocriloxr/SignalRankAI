import { finite, numberLabel, record, rows, type Row } from "../lib/presentation";
import { Card, Notice } from "./ui/primitives";

/** Candlestick chart of one delivered signal: stored candles around the signal with its
 * entry, stop and target levels. Dependency-free SVG; scales to any width. The data is
 * observational and does not prove a fill. */
type Candle = { t: number; o: number; h: number; l: number; c: number };

const W = 960;
const H = 360;
const PAD = { top: 16, right: 76, bottom: 28, left: 8 };

function candlesFrom(chart: Row): Candle[] {
  return rows(chart.candles)
    .map(r => ({ t: finite(r.t), o: finite(r.o), h: finite(r.h), l: finite(r.l), c: finite(r.c) }))
    .filter((c): c is Candle => [c.t, c.o, c.h, c.l, c.c].every(v => v !== null));
}

function firstTarget(value: unknown): number | null {
  if (Array.isArray(value)) return finite(value[0]);
  if (typeof value === "string" && value.trim().startsWith("[")) {
    try { const parsed = JSON.parse(value); return Array.isArray(parsed) ? finite(parsed[0]) : null; } catch { return null; }
  }
  return finite(value);
}

function timeTick(ms: number, timeframe: string): string {
  const d = new Date(ms);
  return timeframe === "1d"
    ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function SignalChart({ data }: { data: Row }) {
  const chart = record(data.chart);
  const signal = record(data.signal);
  const candles = candlesFrom(chart);
  const timeframe = String(chart.timeframe || "");
  const entry = finite(signal.entry);
  const stop = finite(signal.stop_loss);
  const target = firstTarget(signal.take_profit);
  if (candles.length < 5) {
    return <Card id="ws-chart" title="Price chart" eyebrow="Stored market candles">
      <Notice tone="neutral">No stored candles are available for this instrument and timeframe yet.</Notice>
    </Card>;
  }
  const levels = [entry, stop, target].filter((v): v is number => v !== null);
  const lo = Math.min(...candles.map(c => c.l), ...levels);
  const hi = Math.max(...candles.map(c => c.h), ...levels);
  const span = hi - lo || Math.abs(hi) * 0.01 || 1;
  const yMin = lo - span * 0.06;
  const yMax = hi + span * 0.06;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const step = plotW / candles.length;
  const body = Math.max(1, Math.min(10, step * 0.62));
  const y = (v: number) => PAD.top + (yMax - v) / (yMax - yMin) * plotH;
  const x = (i: number) => PAD.left + step * (i + 0.5);
  const signalMs = finite(chart.signal_time_ms);
  const signalIndex = signalMs === null ? -1 : candles.findIndex(c => c.t >= signalMs);
  const ticks = [0, Math.floor(candles.length / 2), candles.length - 1];
  const line = (value: number | null, label: string, cls: string) => value === null ? null :
    <g className={`ws-chart-level ${cls}`}>
      <line x1={PAD.left} x2={W - PAD.right} y1={y(value)} y2={y(value)} />
      <text x={W - PAD.right + 6} y={y(value) + 4}>{label} {numberLabel(value, 5)}</text>
    </g>;
  const last = candles[candles.length - 1];
  return <Card id="ws-chart" title="Price chart" eyebrow={`Stored market candles · ${timeframe || "timeframe unavailable"}`}>
    <figure className="ws-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" preserveAspectRatio="none"
        aria-label={`${String(signal.asset || "Instrument")} ${timeframe} candles with entry, stop and target levels; last close ${numberLabel(last.c, 5)}`}>
        {signalIndex >= 0 && <rect className="ws-chart-after" x={x(signalIndex) - step / 2} y={PAD.top}
          width={W - PAD.right - (x(signalIndex) - step / 2)} height={plotH} />}
        {candles.map((c, i) => {
          const up = c.c >= c.o;
          const top = y(Math.max(c.o, c.c));
          const height = Math.max(1, Math.abs(y(c.o) - y(c.c)));
          return <g key={c.t} className={up ? "ws-candle ws-candle--up" : "ws-candle ws-candle--down"}>
            <line x1={x(i)} x2={x(i)} y1={y(c.h)} y2={y(c.l)} />
            <rect x={x(i) - body / 2} y={top} width={body} height={height} />
          </g>;
        })}
        {line(stop, "Stop", "ws-chart-level--stop")}
        {line(target, "Target", "ws-chart-level--target")}
        {line(entry, "Entry", "ws-chart-level--entry")}
        {ticks.map(i => <text key={i} className="ws-chart-tick" x={x(i)} y={H - 8} textAnchor="middle">
          {timeTick(candles[i].t, timeframe)}</text>)}
      </svg>
      <figcaption className="ui-muted">Shaded area: after the signal was issued. Candles are SignalRank&apos;s stored market data and may differ slightly from your broker&apos;s prices.</figcaption>
    </figure>
  </Card>;
}
