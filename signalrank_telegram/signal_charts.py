from __future__ import annotations

import json
import logging
from io import BytesIO
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Arial.ttf" if not bold else "Arial Bold.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
        if number == number and abs(number) > 0:
            return number
    except Exception:
        pass
    return None


def _parse_take_profit(raw: Any) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[float] = []
        for item in raw:
            value = _as_float(item)
            if value is not None:
                out.append(value)
        return out
    if isinstance(raw, (int, float)):
        value = _as_float(raw)
        return [value] if value is not None else []
    text = str(raw).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [value for value in (_as_float(item) for item in parsed) if value is not None]
        value = _as_float(parsed)
        return [value] if value is not None else []
    except Exception:
        pass
    parts = [part.strip() for part in text.split(",") if part.strip()]
    out: list[float] = []
    for part in parts:
        value = _as_float(part)
        if value is not None:
            out.append(value)
    return out


def _normalize_candles(candles: Iterable[dict[str, Any]]) -> list[dict[str, float]]:
    normalized: list[dict[str, float]] = []
    for candle in candles or []:
        if not isinstance(candle, dict):
            continue
        open_price = _as_float(candle.get("open"))
        high_price = _as_float(candle.get("high"))
        low_price = _as_float(candle.get("low"))
        close_price = _as_float(candle.get("close"))
        if None in {open_price, high_price, low_price, close_price}:
            continue
        normalized.append(
            {
                "timestamp": float(candle.get("timestamp") or 0.0),
                "open": float(open_price),
                "high": float(high_price),
                "low": float(low_price),
                "close": float(close_price),
            }
        )
    normalized.sort(key=lambda item: item["timestamp"])
    return normalized


def render_signal_chart(signal: dict[str, Any], candles: Iterable[dict[str, Any]] | None = None) -> BytesIO | None:
    candles_norm = _normalize_candles(candles or signal.get("recent_ohlcv") or [])
    if not candles_norm:
        return None

    entry = _as_float(signal.get("entry"))
    stop_loss = _as_float(signal.get("stop_loss"))
    take_profit_levels = _parse_take_profit(signal.get("take_profit"))
    last_close = candles_norm[-1]["close"]

    level_values = [value for value in [entry, stop_loss, last_close, *take_profit_levels] if value is not None]
    if not level_values:
        return None

    high_bound = max(max(candle["high"] for candle in candles_norm), max(level_values))
    low_bound = min(min(candle["low"] for candle in candles_norm), min(level_values))
    padding = max((high_bound - low_bound) * 0.12, high_bound * 0.005)
    chart_high = high_bound + padding
    chart_low = max(0.0, low_bound - padding)

    width = 1280
    height = 760
    header_h = 92
    footer_h = 56
    left_pad = 82
    right_pad = 34
    top_pad = header_h
    bottom_pad = footer_h
    plot_top = top_pad + 14
    plot_bottom = height - bottom_pad - 18
    plot_left = left_pad
    plot_right = width - right_pad
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    background = (13, 18, 28)
    panel = (20, 28, 43)
    grid = (43, 54, 70)
    text = (237, 243, 249)
    muted = (162, 174, 191)
    bullish = (52, 211, 153)
    bearish = (248, 113, 113)
    accent = (96, 165, 250)
    tp_color = (74, 222, 128)
    sl_color = (248, 113, 113)

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    font_title = _load_font(26, bold=True)
    font_body = _load_font(18)
    font_small = _load_font(14)

    draw.rounded_rectangle((18, 16, width - 18, height - 16), radius=24, fill=panel, outline=(30, 41, 59), width=2)
    draw.text((34, 28), f"{signal.get('asset') or signal.get('symbol') or 'Signal'}", fill=text, font=font_title)
    meta = f"{str(signal.get('direction') or '').upper()} · {signal.get('timeframe') or '1h'}"
    if signal.get("strategy_name"):
        meta += f" · {signal.get('strategy_name')}"
    draw.text((36, 63), meta, fill=muted, font=font_body)

    # Grid and axes
    grid_lines = 5
    for idx in range(grid_lines + 1):
        y = plot_top + int((plot_height / grid_lines) * idx)
        draw.line((plot_left, y, plot_right, y), fill=grid, width=1)
        price_level = chart_high - ((chart_high - chart_low) * (idx / grid_lines))
        label = f"{price_level:,.4f}" if price_level < 100 else f"{price_level:,.2f}"
        draw.text((24, y - 8), label, fill=muted, font=font_small)

    candle_count = len(candles_norm)
    candle_gap = max(2, plot_width // max(1, candle_count))
    candle_body = max(3, int(candle_gap * 0.58))

    def y_for_price(price: float) -> int:
        if chart_high <= chart_low:
            return plot_bottom
        ratio = (price - chart_low) / (chart_high - chart_low)
        return int(plot_bottom - (ratio * plot_height))

    def x_for_index(index: int) -> int:
        return int(plot_left + (index * candle_gap) + (candle_gap / 2))

    # Candlesticks
    for index, candle in enumerate(candles_norm):
        x = x_for_index(index)
        open_y = y_for_price(candle["open"])
        close_y = y_for_price(candle["close"])
        high_y = y_for_price(candle["high"])
        low_y = y_for_price(candle["low"])
        color = bullish if candle["close"] >= candle["open"] else bearish

        draw.line((x, high_y, x, low_y), fill=color, width=2)
        top = min(open_y, close_y)
        bottom = max(open_y, close_y)
        if bottom == top:
            bottom += 1
        draw.rounded_rectangle(
            (x - candle_body // 2, top, x + candle_body // 2, bottom),
            radius=2,
            fill=color,
            outline=color,
        )

    # Reference lines
    def draw_level(price: float | None, label: str, color: tuple[int, int, int]) -> None:
        if price is None:
            return
        y = y_for_price(price)
        draw.line((plot_left, y, plot_right, y), fill=color, width=2)
        label_text = f"{label} {price:,.2f}" if price >= 100 else f"{label} {price:,.4f}"
        text_width = draw.textbbox((0, 0), label_text, font=font_small)[2]
        box_x = min(plot_right - text_width - 16, plot_left + 8)
        draw.rounded_rectangle((box_x - 6, y - 12, box_x + text_width + 10, y + 12), radius=6, fill=(16, 23, 35))
        draw.text((box_x, y - 9), label_text, fill=color, font=font_small)

    draw_level(entry, "ENTRY", accent)
    draw_level(stop_loss, "SL", sl_color)
    for idx, tp in enumerate(take_profit_levels[:3], 1):
        draw_level(tp, f"TP{idx}", tp_color)

    # Footer stats
    footer_y = height - 40
    footer_parts = []
    if signal.get("regime"):
        footer_parts.append(f"Regime: {signal.get('regime')}")
    if signal.get("score") is not None:
        try:
            footer_parts.append(f"Score: {float(signal.get('score')):.0f}")
        except Exception:
            pass
    if signal.get("rr_ratio") is not None:
        try:
            footer_parts.append(f"RR: {float(signal.get('rr_ratio')):.2f}")
        except Exception:
            pass
    footer_parts.append(f"Last: {last_close:,.2f}" if last_close >= 100 else f"Last: {last_close:,.4f}")
    draw.text((36, footer_y), "  •  ".join(footer_parts), fill=muted, font=font_small)

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    out.seek(0)
    out.name = f"{str(signal.get('signal_id') or signal.get('asset') or 'signal').strip()}.png"
    return out


async def build_signal_chart(signal: dict[str, Any], candles: Iterable[dict[str, Any]] | None = None, limit: int = 60) -> BytesIO | None:
    if candles is None:
        try:
            from data.fetcher import async_get_candles

            asset = str(signal.get("asset") or signal.get("symbol") or "").strip()
            timeframe = str(signal.get("timeframe") or "1h").strip().lower() or "1h"
            fetched = await async_get_candles(asset, timeframe)
            if fetched:
                candles = fetched[-max(20, int(limit)) :]
        except Exception as exc:
            logger.debug("[signal_chart] candle fetch failed: %s", exc)
            candles = signal.get("recent_ohlcv") or []
    return render_signal_chart(signal, candles=candles)
