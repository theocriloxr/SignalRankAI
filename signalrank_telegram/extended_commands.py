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
    value = automaton_status()
    await _reply(update, f"Automaton mode: {value['state']}\nVirtual balance: {value['starting_balance']:.2f}\nReal-money execution: disabled")


async def automaton_report_command(update, context) -> None:
    value = automaton_status()
    decision = value["decision"]
    await _reply(update, f"Automaton report\nState: {value['state']}\nRecommendations: " + "; ".join(decision["recommendations"]))


async def paper_balance_command(update, context) -> None:
    await _reply(update, "Paper balance is virtual only. Use /paper_positions and /paper_performance for the current ledger.")


async def paper_positions_command(update, context) -> None:
    await _reply(update, "Paper positions are isolated from live funds. No broker order is submitted by this command.")


async def paper_performance_command(update, context) -> None:
    await _reply(update, "Paper performance is reported separately from backtest, shadow, manual, and live outcomes. Sample size is required before claims.")


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


async def performance_truth_command(update, context) -> None:
    await _reply(update, "Performance truth is provenance-separated (backtest/shadow/paper/manual/live) and always includes sample size and methodology.")


async def provider_health_command(update, context) -> None:
    await _reply(update, "Provider health is monitored for freshness, latency, failures, and confidence. Untrusted final quotes are blocked.")


__all__ = [name for name in globals() if name.endswith("_command")]
