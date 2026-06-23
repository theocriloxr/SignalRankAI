"""
SignalRankAI — Tier Notification Manager (PERFECTED)

Formats and dispatches all outcome notifications with tier-specific content:
  - FREE: Teaser format, drives upgrade CTA
  - PREMIUM: Full detail, entry/exit/pct, no TP3
  - VIP/ADMIN/OWNER: Full detail + R-multiple + regime + Gemini insight + TP3

One Signal = One Lifecycle:
  BUY BTC → ENTRY HIT → TP1 HIT → TP2 HIT → CLOSED

Every message is edited in-place where possible (edit_message_text)
or sent as a follow-up notification.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _fmt(value, decimals: int = 5) -> str:
    """Format a price/float value nicely."""
    try:
        v = float(value)
        if v == 0:
            return "N/A"
        # Auto-adjust decimal places based on magnitude
        if v >= 1000:
            return f"{v:,.2f}"
        elif v >= 1:
            return f"{v:.{min(decimals, 4)}f}"
        else:
            return f"{v:.{decimals}f}"
    except Exception:
        return str(value) if value else "N/A"


def _pct_str(pct: Optional[float]) -> str:
    """Format a percentage value."""
    if pct is None:
        return "N/A"
    try:
        return f"{float(pct):+.2f}%"
    except Exception:
        return "N/A"


def _r_str(r: Optional[float]) -> str:
    """Format an R-multiple value."""
    if r is None:
        return "N/A"
    try:
        return f"{float(r):.2f}R"
    except Exception:
        return "N/A"


class TierNotificationManager:
    """
    Formats outcome notifications tailored to each subscription tier.

    Tier visibility matrix:
    ┌─────────────┬──────┬─────────┬─────┐
    │ Field       │ FREE │ PREMIUM │ VIP │
    ├─────────────┼──────┼─────────┼─────┤
    │ Asset       │  ✓   │    ✓    │  ✓  │
    │ Direction   │  ✓   │    ✓    │  ✓  │
    │ Entry       │  -   │    ✓    │  ✓  │
    │ TP Level    │  ✓   │    ✓    │  ✓  │
    │ Pct gain    │  -   │    ✓    │  ✓  │
    │ R-Multiple  │  -   │    ✓    │  ✓  │
    │ Current px  │  -   │    ✓    │  ✓  │
    │ TP3 target  │  -   │    -    │  ✓  │
    │ Regime      │  -   │    -    │  ✓  │
    │ AI insight  │  -   │    -    │  ✓  │
    └─────────────┴──────┴─────────┴─────┘
    """

    def format_tp_hit_notification(
        self,
        signal: dict,
        tier: str,
        tp_level: int,
        profit_pct: float,
        current_price: Optional[float] = None,
    ) -> str:
        """Format a TP hit notification for the given tier."""
        tier_l = str(tier or "free").lower()
        if tier_l in ("owner", "admin"):
            tier_l = "vip"

        asset     = str(signal.get("asset") or "?").upper()
        direction = str(signal.get("direction") or "long").upper()
        entry     = signal.get("entry")
        sl        = signal.get("stop_loss")
        strategy  = str(signal.get("strategy_name") or signal.get("strategy") or "")
        regime    = str(signal.get("regime") or "")
        score     = signal.get("score")
        r_mult    = signal.get("r_multiple")

        # Derive R-multiple if not provided
        if r_mult is None and entry and sl:
            try:
                risk = abs(float(entry) - float(sl))
                if risk > 0 and profit_pct:
                    if direction == "LONG":
                        reward = float(entry) * abs(float(profit_pct)) / 100
                    else:
                        reward = float(entry) * abs(float(profit_pct)) / 100
                    r_mult = reward / risk
            except Exception:
                r_mult = None

        tp_emoji_map = {1: "🟢", 2: "💛", 3: "✅"}
        tp_emoji = tp_emoji_map.get(tp_level, "✅")

        tp_label_map = {1: "TP1 HIT", 2: "TP2 HIT", 3: "ALL TARGETS HIT"}
        tp_label = tp_label_map.get(tp_level, f"TP{tp_level} HIT")

        if tier_l == "free":
            return self._format_tp_free(
                asset, direction, tp_level, tp_label, tp_emoji, profit_pct
            )
        elif tier_l == "premium":
            return self._format_tp_premium(
                asset, direction, tp_level, tp_label, tp_emoji,
                profit_pct, entry, current_price, r_mult
            )
        else:  # vip
            return self._format_tp_vip(
                asset, direction, tp_level, tp_label, tp_emoji,
                profit_pct, entry, current_price, r_mult,
                strategy, regime, score
            )

    def _format_tp_free(
        self,
        asset: str,
        direction: str,
        tp_level: int,
        tp_label: str,
        tp_emoji: str,
        profit_pct: float,
    ) -> str:
        """FREE tier: minimal info, strong upgrade CTA."""
        lines = [
            f"{tp_emoji} <b>{tp_label}</b>",
            "",
            f"<b>{asset}</b> {direction}",
            "",
            "🔒 <i>Profit details unlocked for Premium & VIP members.</i>",
            "",
            "📈 Want exact entries, exits & live tracking?",
            "→ Use /upgrade to see the full trade.",
        ]
        return "\n".join(lines)

    def _format_tp_premium(
        self,
        asset: str,
        direction: str,
        tp_level: int,
        tp_label: str,
        tp_emoji: str,
        profit_pct: float,
        entry: Optional[float],
        current_price: Optional[float],
        r_mult: Optional[float],
    ) -> str:
        """PREMIUM tier: full detail with P&L, no regime/AI insight."""
        pct_display = _pct_str(profit_pct)
        r_display = _r_str(r_mult)
        entry_display = _fmt(entry) if entry else "—"
        price_display = _fmt(current_price) if current_price else "—"

        lines = [
            f"{tp_emoji} <b>{tp_label}</b>",
            "",
            f"Asset: <b>{asset}</b>",
            f"Direction: <b>{direction}</b>",
            f"Entry: <b>{entry_display}</b>",
            f"Exit Price: <b>{price_display}</b>",
            "",
            f"Gain: <b>{pct_display}</b>",
            f"Result: <b>{r_display}</b>",
        ]

        if tp_level < 3:
            lines += [
                "",
                "⚡ <i>Position partial-closed. Stop moved to Break-Even.</i>",
                "🎯 <i>Remaining position tracking next target.</i>",
            ]
        else:
            lines += [
                "",
                "🏆 <b>All targets hit — trade fully closed.</b>",
                "Well-managed ✔",
            ]

        return "\n".join(lines)

    def _format_tp_vip(
        self,
        asset: str,
        direction: str,
        tp_level: int,
        tp_label: str,
        tp_emoji: str,
        profit_pct: float,
        entry: Optional[float],
        current_price: Optional[float],
        r_mult: Optional[float],
        strategy: str,
        regime: str,
        score: Optional[float],
    ) -> str:
        """VIP tier: full detail + strategy + regime + R-multiple."""
        pct_display = _pct_str(profit_pct)
        r_display = _r_str(r_mult)
        entry_display = _fmt(entry) if entry else "—"
        price_display = _fmt(current_price) if current_price else "—"
        score_display = f"{float(score):.0f}/100" if score is not None else "—"

        lines = [
            f"{tp_emoji} <b>👑 VIP SIGNAL — {tp_label}</b>",
            "",
            f"Asset: <b>{asset}</b> | Direction: <b>{direction}</b>",
            f"Entry: <b>{entry_display}</b> → Exit: <b>{price_display}</b>",
            "",
            f"📊 Gain: <b>{pct_display}</b> | Result: <b>{r_display}</b>",
            f"Score: <b>{score_display}</b>",
        ]

        if strategy:
            lines.append(f"Strategy: <b>{strategy}</b>")
        if regime:
            lines.append(f"Regime: <b>{regime}</b>")

        if tp_level < 3:
            lines += [
                "",
                "⚡ <b>Partial exit executed.</b>",
                "🛡️ Stop Loss moved to Break-Even.",
                "🎯 Remainder tracking next level.",
            ]
        else:
            lines += [
                "",
                "🏆 <b>FULL CLOSE — ALL TARGETS HIT</b>",
                "Exceptional execution. Profit secured. ✅",
            ]

        return "\n".join(lines)

    def format_sl_hit_notification(
        self,
        signal: dict,
        tier: str,
        loss_pct: float,
        is_break_even: bool = False,
    ) -> str:
        """Format a stop loss / break-even hit notification."""
        tier_l = str(tier or "free").lower()
        if tier_l in ("owner", "admin"):
            tier_l = "vip"

        asset     = str(signal.get("asset") or "?").upper()
        direction = str(signal.get("direction") or "long").upper()
        entry     = signal.get("entry")
        sl        = signal.get("stop_loss")

        if is_break_even:
            # Break-even hit after TP1 — this is actually a positive outcome
            return (
                "🛡️ <b>Break-Even Stop Hit</b>\n\n"
                f"<b>{asset}</b> {direction}\n\n"
                "TP1 was already captured.\n"
                "Remaining position closed at break-even.\n"
                "<b>Capital fully protected. ✅</b>"
            )

        if tier_l == "free":
            return (
                f"❌ <b>Stop Loss Hit</b>\n\n"
                f"<b>{asset}</b> {direction}\n\n"
                "🔒 Upgrade to see full trade details and P&L.\n"
                "→ /upgrade"
            )

        loss_display = _pct_str(abs(loss_pct) * -1)
        entry_display = _fmt(entry) if entry else "—"
        sl_display = _fmt(sl) if sl else "—"

        return (
            f"❌ <b>Stop Loss Hit</b>\n\n"
            f"Asset: <b>{asset}</b> | Direction: <b>{direction}</b>\n"
            f"Entry: <b>{entry_display}</b>\n"
            f"Stop Loss: <b>{sl_display}</b>\n"
            f"\nLoss: <b>{loss_display}</b>\n\n"
            "Risk was predefined and controlled.\n"
            "<i>Awaiting next high-probability setup.</i>"
        )

    def format_signal_update(
        self,
        signal: dict,
        tier: str,
        update_type: str,
        data: dict,
    ) -> str:
        """Format a general signal update notification (invalidation, price update, etc.)."""
        asset     = str(signal.get("asset") or "?").upper()
        direction = str(signal.get("direction") or "long").upper()

        if update_type == "invalidated":
            reason = str(data.get("reason") or "Market conditions changed")
            return (
                f"⚠️ <b>Signal Invalidated</b>\n\n"
                f"<b>{asset}</b> {direction}\n\n"
                f"Reason: {reason}\n\n"
                "<i>Risk management: trade closed at market, no loss incurred.</i>"
            )

        if update_type == "entry_filled":
            fill_price = data.get("fill_price")
            sl = signal.get("stop_loss")
            return (
                f"⚡ <b>Entry Filled</b>\n\n"
                f"<b>{asset}</b> {direction}\n"
                f"Entry: <b>{_fmt(fill_price)}</b>\n"
                f"Stop Loss: <b>{_fmt(sl)}</b>\n\n"
                "<i>Trade is now live. Monitoring targets.</i>"
            )

        if update_type == "be_moved":
            new_sl = data.get("new_sl")
            return (
                f"🛡️ <b>Stop Moved to Break-Even</b>\n\n"
                f"<b>{asset}</b> {direction}\n"
                f"New Stop: <b>{_fmt(new_sl)}</b> (Break-Even)\n\n"
                "<i>TP1 secured. Capital now protected.</i>"
            )

        return f"ℹ️ Signal update: {asset} {direction} — {update_type}"

    def format_entry_filled_notification(
        self,
        signal: dict,
        tier: str,
        fill_price: float,
    ) -> str:
        """Format entry-filled notification."""
        return self.format_signal_update(
            signal, tier, "entry_filled",
            {"fill_price": fill_price}
        )

    def format_daily_performance_summary(
        self,
        stats: dict,
        tier: str,
    ) -> str:
        """Format daily performance summary."""
        tier_l = str(tier or "free").lower()
        total = int(stats.get("total") or 0)
        wins  = int(stats.get("wins") or 0)
        losses = int(stats.get("losses") or 0)
        win_rate = float(stats.get("win_rate") or 0) * 100
        net_r = float(stats.get("net_r") or 0)
        best_asset = str(stats.get("best_asset") or "—")
        profit_loss_pct = float(stats.get("profit_loss_pct") or 0)

        if total == 0:
            return (
                "📊 <b>Daily Performance Summary</b>\n\n"
                "No signal outcomes recorded today.\n\n"
                "<i>Quality over quantity.</i>"
            )

        if tier_l == "free":
            return (
                "📊 <b>Signal Update</b>\n\n"
                f"Signals active today: <b>{total}</b>\n\n"
                "🔒 Upgrade for detailed win rate, P&L & strategy breakdown.\n"
                "→ /upgrade"
            )

        lines = [
            "📊 <b>Daily Performance Summary</b>",
            "",
            f"Signals: <b>{total}</b> | Wins: <b>{wins}</b> | Losses: <b>{losses}</b>",
            f"Win Rate: <b>{win_rate:.1f}%</b>",
            f"Net Result: <b>{_r_str(net_r)}</b>",
            f"P/L: <b>{_pct_str(profit_loss_pct)}</b>",
        ]

        if tier_l in ("vip",) and best_asset:
            lines.append(f"Best Asset: <b>{best_asset}</b>")

        lines += ["", "<i>Consistency over frequency.</i>"]
        return "\n".join(lines)


__all__ = ["TierNotificationManager"]