"use client";

import { useEffect, useRef, useState } from "react";
import client from "../lib/client";
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

function targetsFrom(value: unknown): number[] {
  let list: unknown[] = [];
  if (Array.isArray(value)) list = value;
  else if (typeof value === "string" && value.trim().startsWith("[")) {
    try { const parsed = JSON.parse(value); list = Array.isArray(parsed) ? parsed : []; } catch { list = []; }
  } else list = [value];
  return list.map(item => finite(typeof item === "object" && item !== null ? record(item).price : item))
    .filter((v): v is number => v !== null).slice(0, 3);
}

function timeTick(ms: number, timeframe: string): string {
  const d = new Date(ms);
  return timeframe === "1d"
    ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** How often to ask for new bars: often enough to watch a 5m bar form, rarely for daily bars. */
function pollMs(timeframe: string): number {
  return ["1m", "5m", "15m"].includes(timeframe) ? 15_000 : timeframe === "30m" ? 30_000 : 60_000;
}

/** Merge newer candles into the series; a bar with the same open time replaces the stored one. */
export function mergeCandles(current: Candle[], incoming: Candle[], limit = 400): Candle[] {
  const byTime = new Map(current.map(c => [c.t, c]));
  for (const c of incoming) byTime.set(c.t, c);
  return [...byTime.values()].sort((a, b) => a.t - b.t).slice(-limit);
}

type Live = { candles: Candle[]; lastPrice: number | null; updatedAt: string | null; status: string; closed: boolean };

/** Live candle flow (owner request, 8 Nov 2026): polls the signal's candle endpoint while the tab is
 * visible and the trade is not closed, so the chart keeps moving with the market. */
function useLiveCandles(signalId: string, timeframe: string, initial: Candle[], closedAtStart: boolean): Live {
  const [live, setLive] = useState<Live>({ candles: initial, lastPrice: null, updatedAt: null, status: "", closed: closedAtStart });
  const latest = useRef(live);
  useEffect(() => { latest.current = live; }, [live]);
  useEffect(() => {
    if (!signalId || closedAtStart) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      if (stopped) return;
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        timer = setTimeout(tick, pollMs(timeframe)); return;
      }
      const series = latest.current.candles;
      const after = series.length ? series[series.length - 1].t : 0;
      try {
        const response = await client.GET("/api/v1/platform/signals/{signal_id}/candles", {
          params: { path: { signal_id: signalId }, query: { after_ms: after } },
        });
        const body = record(response.data);
        if (response.response.ok && !stopped) {
          const incoming = candlesFrom(body);
          const status = record(body.trade_status);
          setLive(prev => ({
            candles: mergeCandles(prev.candles, incoming),
            lastPrice: finite(body.last_price),
            updatedAt: typeof body.server_time === "string" ? body.server_time : null,
            status: typeof status.label === "string" ? status.label : prev.status,
            closed: body.closed === true,
          }));
          if (body.closed === true) return;
        }
      } catch { /* a missed poll is retried on the next tick */ }
      timer = setTimeout(tick, pollMs(timeframe));
    };
    timer = setTimeout(tick, 2_000);
    const wake = () => { if (document.visibilityState === "visible") { if (timer) clearTimeout(timer); timer = setTimeout(tick, 250); } };
    document.addEventListener("visibilitychange", wake);
    return () => { stopped = true; if (timer) clearTimeout(timer); document.removeEventListener("visibilitychange", wake); };
  }, [signalId, timeframe, closedAtStart]);
  return live;
}

export function SignalChart({ data }: { data: Row }) {
  const chart = record(data.chart);
  const signal = record(data.signal);
  const timeframe = String(chart.timeframe || "");
  const tradeStatus = record(signal.trade_status);
  const live = useLiveCandles(String(signal.signal_id || ""), timeframe, candlesFrom(chart), tradeStatus.closed === true);
  const candles = live.candles;
  const entry = finite(signal.entry);
  const stop = finite(signal.stop_loss);
  const targets = targetsFrom(signal.take_profit);
  if (candles.length < 5) {
    return <Card id="ws-chart" title="Price chart">
      <Notice tone="neutral">We don&rsquo;t have price history for this instrument and timeframe yet.</Notice>
    </Card>;
  }
  const levels = [entry, stop, ...targets].filter((v): v is number => v !== null);
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
  const livePrice = !live.closed && live.lastPrice !== null && live.lastPrice >= yMin && live.lastPrice <= yMax ? live.lastPrice : null;
  const updated = live.updatedAt ? new Date(live.updatedAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : null;
  return <Card id="ws-chart" title="Price chart" eyebrow={timeframe ? `${timeframe} candles` : undefined}>
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
        {targets.map((t, i) => <g key={i}>{line(t, targets.length > 1 ? `TP${i + 1}` : "Target", "ws-chart-level--target")}</g>)}
        {line(entry, "Entry", "ws-chart-level--entry")}
        {livePrice !== null && line(livePrice, "Now", "ws-chart-level--live")}
        {ticks.map(i => <text key={i} className="ws-chart-tick" x={x(i)} y={H - 8} textAnchor="middle">
          {timeTick(candles[i].t, timeframe)}</text>)}
      </svg>
      <figcaption className="ui-muted">
        {live.closed ? "This trade is closed; the chart shows its full path. " : <>
          <span className="ws-chart-live" aria-live="polite"><span className="ws-chart-live-dot" aria-hidden="true"/>Live{updated ? ` · updated ${updated}` : " · connecting"}{live.status ? ` · ${live.status}` : ""}</span>{" "}</>}
        The shaded part is after the signal was sent. The last bar may still be forming. Prices can differ slightly from your broker&rsquo;s.</figcaption>
    </figure>
  </Card>;
}
