"""Small, safe command adapters for public testing and owner diagnostics."""

from __future__ import annotations

import os
from typing import Any

from core.automaton import status as automaton_status
from core.release_guard import public_test_status, evaluate_release
from payments.payout_readiness import payout_readiness_status
from payments.receipt_service import receipt_service


async def _reply(update: Any, text: str) -> None:
    target = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if target is not None and hasattr(target, "reply_text"):
        await target.reply_text(text)


async def public_test_status_command(update, context) -> None:
    value = public_test_status()
    await _reply(update, "Public testing: {mode}\nVerdict: {verdict}\nAuto trading disabled: {auto}\nCopy trading disabled: {copy}\nPayments enabled: {payments}".format(mode=value["public_testing_mode"], verdict=value["verdict"], auto=value["auto_trading_disabled"], copy=value["copy_trading_disabled"], payments=value["payments_enabled"]))


async def release_guard_command(update, context) -> None:
    report = evaluate_release()
    failed = [check.name for check in report.checks if not check.ok]
    suffix = "" if not failed else "\nBlocked checks: " + ", ".join(failed)
    await _reply(update, f"Release guard: {report.verdict}{suffix}")


async def automaton_status_command(update, context) -> None:
    """Compatibility alias for the per-user automatic paper-trading status."""
    from core.paper_trading_service import paper_trading_service
    uid = _telegram_user_id(update)
    snapshot = await paper_trading_service.snapshot(uid)
    if snapshot is None:
        await _reply(update, "Send /start first so your paper account can be created.")
        return
    await _reply(
        update,
        "Automatic Paper Trading\n"
        f"State: {'RUNNING' if snapshot.auto_trade_enabled else 'PAUSED'}\n"
        f"Equity: {_money(snapshot.equity)}\n"
        f"Open positions: {snapshot.open_positions}\n"
        "Broker execution is separate and never triggered by this command.",
    )


async def automaton_report_command(update, context) -> None:
    value = automaton_status()
    decision = value["decision"]
    await _reply(update, f"Automaton report\nState: {value['state']}\nRecommendations: " + "; ".join(decision["recommendations"]))


def _telegram_user_id(update: Any) -> int:
    return int(getattr(getattr(update, "effective_user", None), "id", 0) or 0)


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"


async def paper_balance_command(update, context) -> None:
    """Show the virtual account or initialize a new balance."""
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    if not uid:
        return
    args = list(getattr(context, "args", []) or [])
    snapshot = await paper_trading_service.snapshot(uid)
    if snapshot is None:
        await _reply(update, "Send /start first so your paper account can be created.")
        return
    if args:
        try:
            requested = float(args[0])
        except Exception:
            await _reply(update, "Usage: /paper_balance or /paper_balance 10000")
            return
        if snapshot.open_positions:
            await _reply(update, "Close or wait for your open paper positions before changing the starting balance.")
            return
        if snapshot.closed_positions:
            await _reply(update, f"This account already has history. Use /paper_reset {requested:g} CONFIRM to reset it safely.")
            return
        snapshot = await paper_trading_service.reset_account(uid, requested)
        if snapshot is None:
            await _reply(update, "Paper account could not be initialized.")
            return
    await _reply(
        update,
        "📄 Paper Account\n\n"
        f"Starting balance: {_money(snapshot.starting_balance)}\n"
        f"Cash available: {_money(snapshot.cash_balance)}\n"
        f"Reserved in positions: {_money(snapshot.reserved_cash)}\n"
        f"Unrealized P&L: {_money(snapshot.unrealized_pnl)}\n"
        f"Realized P&L: {_money(snapshot.realized_pnl)}\n"
        f"Current equity: {_money(snapshot.equity)}\n"
        f"Open positions: {snapshot.open_positions}\n"
        f"Automatic paper trading: {'ON' if snapshot.auto_trade_enabled else 'OFF'}\n\n"
        "Virtual funds only. No broker order is submitted.",
    )


async def paper_positions_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    rows = await paper_trading_service.list_positions(uid, status="open", limit=20)
    if not rows:
        await _reply(update, "No open paper positions. Turn automatic entries on with /paper_settings auto on.")
        return
    lines = ["📈 Open Paper Positions", ""]
    for row in rows:
        pnl = float(row.get("unrealized_pnl") or 0.0)
        lines.extend([
            f"{row['asset']} {str(row['direction']).upper()} • {row.get('timeframe') or '—'}",
            f"Entry {row['fill_entry']:.6g} • Live {row['current_price']:.6g}",
            f"SL {row['stop_loss']:.6g} • Target {float(row.get('target_price') or 0):.6g}",
            f"Unrealized: {pnl:+.2f} • Signal {str(row['signal_id'])[:12]}",
            "",
        ])
    await _reply(update, "\n".join(lines).strip())


async def paper_performance_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    result = await paper_trading_service.performance(uid)
    if not result:
        await _reply(update, "Paper performance is unavailable. Send /start first.")
        return
    snap = result["snapshot"]
    pf = result.get("profit_factor", 0.0)
    pf_text = "∞" if pf == float("inf") else f"{float(pf):.2f}"
    await _reply(
        update,
        "📊 Paper Performance\n\n"
        f"Closed trades: {result['sample_size']}\n"
        f"Wins / losses / flat: {result['wins']} / {result['losses']} / {result['flat']}\n"
        f"Win rate: {result['win_rate_pct']:.1f}%\n"
        f"Net P&L: {result['net_pnl']:+.2f}\n"
        f"Return: {result['return_pct']:+.2f}%\n"
        f"Average R: {result['avg_r']:+.2f}R\n"
        f"Profit factor: {pf_text}\n"
        f"Current equity: {_money(snap['equity'])}\n\n"
        "Paper results are reported separately from delivered-signal, shadow, backtest, demo, and live execution results.",
    )


async def paper_history_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    args = list(getattr(context, "args", []) or [])
    try:
        limit = max(1, min(50, int(args[0]))) if args else 10
    except Exception:
        limit = 10
    rows = await paper_trading_service.list_positions(uid, status="closed", limit=limit)
    skipped = await paper_trading_service.list_positions(uid, status="skipped", limit=min(limit, 10))
    if not rows and not skipped:
        await _reply(update, "No paper history yet.")
        return
    lines = ["🧾 Paper Trade History", ""]
    for row in rows:
        lines.append(
            f"{row['asset']} {str(row['direction']).upper()} • {row.get('exit_reason') or 'CLOSED'} • "
            f"P&L {float(row.get('realized_pnl') or 0):+.2f} • "
            f"{float(row.get('r_multiple') or 0):+.2f}R"
        )
    if skipped:
        lines.extend(["", "Recent skipped delivered signals:"])
        for row in skipped[:5]:
            lines.append(f"• {row['asset']} — {row.get('exit_reason') or 'not eligible'}")
    await _reply(update, "\n".join(lines))


async def paper_reset_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    args = list(getattr(context, "args", []) or [])
    if len(args) < 2 or str(args[-1]).strip().upper() != "CONFIRM":
        await _reply(update, "Reset deletes paper positions and history. Usage: /paper_reset 10000 CONFIRM")
        return
    try:
        balance = float(args[0])
        snapshot = await paper_trading_service.reset_account(uid, balance)
    except ValueError as exc:
        await _reply(update, f"Paper reset blocked: {exc}")
        return
    except Exception:
        await _reply(update, "Paper reset failed. No live funds or broker positions were affected.")
        return
    await _reply(update, f"✅ Paper account reset to {_money(snapshot.starting_balance if snapshot else balance)}.")


async def paper_close_all_command(update, context) -> None:
    """Close all open virtual positions at fresh quotes after explicit confirmation."""
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    args = [str(x).strip().upper() for x in (getattr(context, "args", []) or [])]
    force = args == ["FORCE", "CONFIRM"]
    if args not in (["CONFIRM"], ["FORCE", "CONFIRM"]):
        await _reply(
            update,
            "This closes every open virtual position at the latest trusted quote. "
            "Usage: /paper_close_all CONFIRM\n"
            "Recovery fallback: /paper_close_all FORCE CONFIRM uses only a paper position's fresh last mark when a live quote is unavailable.",
        )
        return
    result = await paper_trading_service.close_all_positions(
        uid,
        allow_last_mark_fallback=force,
        reason="MANUAL_CLOSE_ALL_FORCE" if force else "MANUAL_CLOSE_ALL",
    )
    await _reply(
        update,
        "📄 Paper close-all completed\n\n"
        f"Open before command: {result['open']}\n"
        f"Closed: {result['closed']}\n"
        f"Still open (quote/DB failure): {result['failed']}\n\n"
        "Run /paper_positions to verify, then /paper_reset <balance> CONFIRM when none remain.",
    )


async def paper_settings_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    args = [str(x).strip() for x in (getattr(context, "args", []) or []) if str(x).strip()]
    if args:
        key = args[0].lower()
        try:
            if key == "auto" and len(args) >= 2:
                value = args[1].lower() in {"on", "1", "true", "yes"}
                persisted = await paper_trading_service.update_settings(uid, auto_trade_enabled=value)
                if persisted is None or bool(persisted.auto_trade_enabled) is not bool(value):
                    await _reply(update, "Paper setting was not persisted. Automatic entries were not changed.")
                    return
            elif key == "risk" and len(args) >= 2:
                await paper_trading_service.update_settings(uid, risk_pct=float(args[1]))
            elif key in {"max", "max_positions"} and len(args) >= 2:
                await paper_trading_service.update_settings(uid, max_open_positions=int(args[1]))
            elif key in {"min_score", "score"} and len(args) >= 2:
                await paper_trading_service.update_settings(uid, min_signal_score=float(args[1]))
            elif key in {"spread", "slippage", "fee"} and len(args) >= 2:
                await paper_trading_service.update_settings(uid, **{f"{key}_bps": float(args[1])})
            elif key == "target" and len(args) >= 2:
                await paper_trading_service.update_settings(uid, target_mode=args[1])
            elif key in {"direction", "directions"} and len(args) >= 2:
                await paper_trading_service.update_settings(uid, allowed_directions=args[1])
            elif key in {"assets", "asset_classes"} and len(args) >= 2:
                raw = ",".join(args[1:])
                classes = [] if raw.lower() in {"all", "any", "*"} else [x.strip() for x in raw.split(",") if x.strip()]
                await paper_trading_service.update_settings(uid, allowed_asset_classes=classes)
            else:
                await _reply(
                    update,
                    "Paper settings usage:\n"
                    "/paper_settings auto on|off\n"
                    "/paper_settings risk 1\n"
                    "/paper_settings max_positions 5\n"
                    "/paper_settings min_score 80\n"
                    "/paper_settings target tp1|tp2|tp3\n"
                    "/paper_settings direction both|long|short\n"
                    "/paper_settings asset_classes crypto,fx,stock,index,commodity\n"
                    "/paper_settings spread 2\n"
                    "/paper_settings slippage 2\n"
                    "/paper_settings fee 5",
                )
                return
        except (ValueError, TypeError) as exc:
            await _reply(update, f"Invalid paper setting: {exc}")
            return
    snapshot = await paper_trading_service.snapshot(uid)
    if snapshot is None:
        await _reply(update, "Send /start first so your paper account can be created.")
        return
    classes = ", ".join(snapshot.allowed_asset_classes) if snapshot.allowed_asset_classes else "all"
    await _reply(
        update,
        "⚙️ Paper Trading Settings\n\n"
        f"Automatic entries: {'ON' if snapshot.auto_trade_enabled else 'OFF'}\n"
        f"Risk per signal: {snapshot.risk_pct:.2f}%\n"
        f"Maximum open positions: {snapshot.max_open_positions}\n"
        f"Minimum signal score: {snapshot.min_signal_score:.1f}\n"
        f"Exit target: {snapshot.target_mode}\n"
        f"Directions: {snapshot.allowed_directions}\n"
        f"Asset classes: {classes}\n"
        f"Spread / slippage / fee: {snapshot.spread_bps:.1f} / {snapshot.slippage_bps:.1f} / {snapshot.fee_bps:.1f} bps\n\n"
        "Automatic paper entries use only signals confirmed as delivered to your Telegram account.",
    )


async def paper_status_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    detail = await paper_trading_service.status_detail(uid)
    if detail is None:
        await _reply(update, "Send /start first so your paper account can be created.")
        return
    snap = detail["snapshot"]
    counts = detail.get("recent_counts") or {}
    last = detail.get("last_decision") or {}
    classes = ", ".join(snap.get("allowed_asset_classes") or []) or "all"
    await _reply(
        update,
        "📄 Paper Trading Status\n\n"
        f"Globally available: {'YES' if detail.get('globally_available') else 'NO'}\n"
        f"Account: active\nAutomatic entries: {'ON' if snap.get('auto_trade_enabled') else 'OFF'}\n"
        f"Starting balance: {_money(snap.get('starting_balance'))}\n"
        f"Available cash: {_money(snap.get('cash_balance'))}\nEquity: {_money(snap.get('equity'))}\n"
        f"Risk: {float(snap.get('risk_pct') or 0):.2f}%\n"
        f"Open positions: {snap.get('open_positions')}/{snap.get('max_open_positions')}\n"
        f"Minimum score: {float(snap.get('min_signal_score') or 0):.1f}\n"
        f"Target: {snap.get('target_mode')}\nDirections: {snap.get('allowed_directions')}\n"
        f"Asset classes: {classes}\n"
        f"Last worker scan: {detail.get('worker_last_scan') or 'not observed in this process'}\n"
        f"Last decision: {last.get('decision') or 'none'} — {last.get('reason') or 'none'}\n"
        f"Recent opened/skipped/deferred/failed: {counts.get('opened', 0)}/"
        f"{counts.get('skipped', 0)}/{counts.get('deferred', 0)}/{counts.get('failed', 0)}"
    )


async def paper_activity_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    rows = await paper_trading_service.list_attempts(uid, limit=20)
    if not rows:
        await _reply(update, "No automatic paper-trading decisions recorded yet.")
        return
    lines = ["📋 Paper Activity", ""]
    for row in rows:
        retry = "retryable" if row["retryable"] else "final"
        lines.append(
            f"📌 {row['display_id']} • {row['asset']} • {row['decision']} • "
            f"{row['reason']} • {retry} • {row['created_at']}"
        )
    await _reply(update, "\n".join(lines)[:3900])


async def paper_skips_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    rows = await paper_trading_service.list_attempts(uid, decision="SKIPPED", limit=20)
    if not rows:
        await _reply(update, "No skipped paper signals.")
        return
    lines = ["⚠️ Skipped Paper Signals", ""]
    for row in rows:
        lines.append(f"📌 {row['display_id']} • {row['asset']} • {row['reason']}")
    await _reply(update, "\n".join(lines)[:3900])


async def paper_retry_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service

    uid = _telegram_user_id(update)
    args = [str(value).strip() for value in (getattr(context, "args", []) or []) if str(value).strip()]
    if not args:
        await _reply(update, "Usage: /paper_retry <signal_id>")
        return
    accepted, reason = await paper_trading_service.request_retry(uid, args[0])
    await _reply(update, ("✅ " if accepted else "⚠️ ") + reason)

async def receipt_command(update, context) -> None:
    args = getattr(context, "args", []) or []
    receipt = receipt_service.get(args[0]) if args else None
    await _reply(update, receipt.text_body if receipt else "No confirmed receipt found. Receipts are created only after verified successful payment.")


async def receipts_command(update, context) -> None:
    uid = getattr(getattr(update, "effective_user", None), "id", 0) or 0
    receipts = receipt_service.list_for_user(int(uid))
    await _reply(update, "\n".join(r.receipt_number for r in receipts) if receipts else "No confirmed receipts found.")


async def report_issue_command(update, context) -> None:
    await _reply(update, "Please describe the issue (stale signal, button, payment, receipt, profile, or outcome). Do not send credentials or secrets.")


async def payment_help_command(update, context) -> None:
    await _reply(update, "Payment help: include your Paystack reference and account ID. Never send card, bank, API-key, or broker credentials. Use /support for escalation.")


async def refund_request_command(update, context) -> None:
    await _reply(update, "Refund requests are reviewed manually after payment verification. Send the Paystack reference through /support; no automatic payout is performed.")


async def contact_admin_command(update, context) -> None:
    await _reply(update, "Contact support with /support. Include the command, timestamp, and a short description; do not include secrets or credentials.")


async def tester_feedback_command(update, context) -> None:
    await _reply(update, "Tester feedback categories: bad/stale signal, broken button, payment/receipt, profile, or wrong outcome. Describe what happened and include the signal ID if available.")


async def automaton_pause_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service
    uid = _telegram_user_id(update)
    await paper_trading_service.update_settings(uid, auto_trade_enabled=False)
    await _reply(update, "⏸ Automatic paper entries paused. Existing paper positions will continue to be marked and closed at their configured exits.")


async def automaton_resume_command(update, context) -> None:
    from core.paper_trading_service import paper_trading_service
    uid = _telegram_user_id(update)
    await paper_trading_service.update_settings(uid, auto_trade_enabled=True)
    await _reply(update, "▶️ Automatic paper entries resumed for future Telegram-confirmed signals.")


async def automaton_reset_paper_command(update, context) -> None:
    await _reply(update, "Use /paper_reset <balance> CONFIRM. This deletes user-visible paper positions and starts a new virtual account history without touching any broker.")


async def codexops_command(update, context) -> None:
    command = str(getattr(getattr(update, "message", None), "text", "") or "").split(maxsplit=1)[0].lstrip("/") or "codex_audit"
    await _reply(update, f"CodexOps {command}: READ_ONLY_AUDIT mode. No production writes, deployments, payments, secrets, or trades are permitted.")


async def performance_truth_command(update, context) -> None:
    await _reply(update, "Performance truth is provenance-separated (backtest/shadow/paper/manual/live) and always includes sample size and methodology.")


async def provider_health_command(update, context) -> None:
    await _reply(update, "Provider health is monitored for freshness, latency, failures, and confidence. Untrusted final quotes are blocked.")


__all__ = [name for name in globals() if name.endswith("_command")]
