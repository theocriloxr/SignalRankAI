from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


TARGET_TABLES = {
    "signals",
    "signal_deliveries",
    "outcomes",
    "mt5_credentials",
    "active_signal_messages",
    "users",
}


def _parse_copy_dump(path: Path, tables: set[str]) -> dict[str, list[dict[str, str | None]]]:
    rows: dict[str, list[dict[str, str | None]]] = {name: [] for name in tables}
    current: str | None = None
    current_cols: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for line in fh:
            if line.startswith("COPY public."):
                name = line.split("COPY public.", 1)[1].split(" ", 1)[0]
                if name in tables:
                    current = name
                    col_text = line.split("(", 1)[1].split(") FROM stdin", 1)[0]
                    current_cols = [part.strip() for part in col_text.split(",")]
                else:
                    current = None
                    current_cols = []
                continue
            if current is None:
                continue
            if line == "\\.\n":
                current = None
                current_cols = []
                continue
            raw_values = next(csv.reader([line], delimiter="\t", quotechar="\x07"))
            values = [None if value == r"\N" else value for value in raw_values]
            rows[current].append(dict(zip(current_cols, values)))
    return rows


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        try:
            return datetime.strptime(value.split(".", 1)[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def analyze_dump(path: Path) -> dict[str, Any]:
    rows = _parse_copy_dump(path, TARGET_TABLES)
    signals = {str(row.get("signal_id") or ""): row for row in rows["signals"]}
    table_counts = {name: len(value) for name, value in rows.items()}

    scores = [_f(row.get("score")) for row in rows["signals"] if row.get("score") is not None]
    score_summary = {
        "count": len(scores),
        "min": min(scores) if scores else None,
        "max": max(scores) if scores else None,
        "score_100_count": sum(1 for score in scores if score >= 99.999),
    }

    sent: list[tuple[str, str, datetime, str]] = []
    for delivery in rows["signal_deliveries"]:
        if str(delivery.get("sent_ok") or "").lower() not in {"t", "true", "1"}:
            continue
        signal = signals.get(str(delivery.get("signal_id") or ""), {})
        asset = str(signal.get("asset") or "").upper().strip()
        delivered_at = _dt(delivery.get("delivered_at") or delivery.get("created_at"))
        if asset and delivered_at:
            sent.append((str(delivery.get("user_id") or ""), asset, delivered_at, str(delivery.get("signal_id") or "")))
    sent.sort(key=lambda item: (item[0], item[1], item[2]))
    same_asset_duplicates = []
    for prev, current in zip(sent, sent[1:]):
        if prev[0] == current[0] and prev[1] == current[1] and current[2] - prev[2] <= timedelta(hours=12):
            same_asset_duplicates.append(
                {
                    "user_id": current[0],
                    "asset": current[1],
                    "previous_signal_id": prev[3],
                    "current_signal_id": current[3],
                    "previous_at": prev[2].isoformat(),
                    "current_at": current[2].isoformat(),
                }
            )

    win_status = {"tp", "tp1", "tp2", "tp3", "partial_tp", "partial", "win"}
    loss_status = {"sl", "loss", "stop_loss"}
    outcome_counts = Counter()
    segment_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for outcome in rows["outcomes"]:
        status = str(outcome.get("canonical_outcome") or outcome.get("status") or "").lower()
        signal = signals.get(str(outcome.get("signal_id") or ""), {})
        asset_class = str(signal.get("asset_class") or "unknown").lower()
        timeframe = str(signal.get("timeframe") or "unknown").lower()
        if status in win_status or status.startswith("tp"):
            bucket = "win"
        elif status in loss_status:
            bucket = "loss"
        elif "time" in status or status == "expired":
            bucket = "time_stop"
        else:
            bucket = status or "unknown"
        outcome_counts[bucket] += 1
        segment_counts[f"{asset_class}/{timeframe}"][bucket] += 1

    mt5 = []
    for row in rows["mt5_credentials"]:
        mt5.append(
            {
                "user_id": row.get("user_id"),
                "login_present": bool(row.get("mt5_login")),
                "server_present": bool(row.get("server")),
                "metaapi_account_id_present": bool(row.get("metaapi_account_id")),
                "updated_at": row.get("updated_at"),
            }
        )

    findings = []
    if same_asset_duplicates:
        findings.append(f"{len(same_asset_duplicates)} sent_ok same-user/same-asset deliveries occurred within 12h.")
    terminal = outcome_counts["win"] + outcome_counts["loss"]
    if terminal:
        wr = outcome_counts["win"] / terminal * 100.0
        if wr < 45.0:
            findings.append(f"Terminal tracked win rate is {wr:.1f}% ({outcome_counts['win']}W/{outcome_counts['loss']}L).")
    if score_summary["score_100_count"]:
        findings.append(f"{score_summary['score_100_count']} signals scored 100; inspect max_score_raw logs and score calibration.")

    return {
        "table_counts": table_counts,
        "score_summary": score_summary,
        "signals_by_asset_class": dict(Counter(str(row.get("asset_class") or "unknown") for row in rows["signals"])),
        "signals_by_timeframe": dict(Counter(str(row.get("timeframe") or "unknown") for row in rows["signals"])),
        "outcome_counts": dict(outcome_counts),
        "outcome_segments": {key: dict(value) for key, value in segment_counts.items()},
        "same_asset_duplicate_12h_count": len(same_asset_duplicates),
        "same_asset_duplicate_12h_examples": same_asset_duplicates[:20],
        "active_signal_messages": dict(Counter(str(row.get("is_active") or "unknown") for row in rows["active_signal_messages"])),
        "mt5_credentials": mt5,
        "findings": findings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a Railway PostgreSQL plain SQL dump for SignalRankAI delivery/outcome issues.")
    parser.add_argument("dump", type=Path, help="Path to railway_data.sql")
    parser.add_argument("--json", action="store_true", help="Print full JSON instead of a concise report")
    args = parser.parse_args()
    report = analyze_dump(args.dump)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return
    print("Railway dump analysis")
    print("====================")
    print("Tables:", json.dumps(report["table_counts"], sort_keys=True))
    print("Scores:", json.dumps(report["score_summary"], sort_keys=True))
    print("Outcomes:", json.dumps(report["outcome_counts"], sort_keys=True))
    print(f"Same-user/same-asset <12h duplicates: {report['same_asset_duplicate_12h_count']}")
    print("MT5:", json.dumps(report["mt5_credentials"], sort_keys=True))
    if report["findings"]:
        print("Findings:")
        for finding in report["findings"]:
            print(f"- {finding}")


if __name__ == "__main__":
    main()

