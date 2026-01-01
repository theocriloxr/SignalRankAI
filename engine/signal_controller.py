from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from uuid import uuid4

from engine.risk import calculate_dynamic_risk
from engine.scoring import calculate_signal_score


Signal = Dict[str, Any]


@dataclass(frozen=True)
class ControllerDecision:
    approved: List[Signal]
    discarded: List[Signal]


class SignalController:
    """Single authoritative gatekeeper for signal approval.

    This module is the only place that should decide which candidate strategy
    signals are approved for persistence/dispatch.
    """

    # Score thresholds
    PREMIUM_THRESHOLD: int = 75
    VIP_THRESHOLD: int = 85

    def __init__(self) -> None:
        self._kill_switch_enabled: bool = False
        self.KILL_SWITCH: Dict[str, Any] = {"enabled": False, "reason": ""}

        # Legacy per-cycle dedupe support (used by older pipeline code)
        self._cycle_seen: Set[Tuple[str, str, str]] = set()

        # Minimal audit logger (kept for existing code/tests)
        import logging

        self.audit_logger = logging.getLogger("audit")
        self.audit_logger.setLevel(logging.INFO)
        if not self.audit_logger.handlers:
            handler = logging.FileHandler("audit.log")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.audit_logger.addHandler(handler)

    def enable_kill_switch(self, reason: str = "manual", admin_id: Optional[int] = None) -> None:
        self._kill_switch_enabled = True
        self.KILL_SWITCH["enabled"] = True
        self.KILL_SWITCH["reason"] = reason
        self.audit_logger.warning(f"KILL SWITCH ENABLED by {admin_id}: {reason}")

    def disable_kill_switch(self, admin_id: Optional[int] = None) -> None:
        self._kill_switch_enabled = False
        self.KILL_SWITCH["enabled"] = False
        self.KILL_SWITCH["reason"] = ""
        self.audit_logger.info(f"KILL SWITCH DISABLED by {admin_id}")

    def is_kill_switch_enabled(self) -> bool:
        return self._kill_switch_enabled

    # --- Legacy API (kept for current codebase + unit tests) ---
    def log_audit_event(self, event: str, user_id: Optional[int] = None, details: Any = None) -> None:
        msg = f"EVENT: {event}"
        if user_id is not None:
            msg += f" | user_id={user_id}"
        if details is not None:
            msg += f" | details={details}"
        self.audit_logger.info(msg)

    def deduplicate_signals(self, signals: List[Signal]) -> List[Signal]:
        return self._dedupe([self._normalize_signal(s) for s in signals if s])

    def cap_correlation(self, signals: List[Signal]) -> List[Signal]:
        # Placeholder correlation cap: one per asset (highest score wins)
        best: Dict[str, Signal] = {}
        for s in signals:
            asset = str(s.get("asset") or "")
            if not asset:
                continue
            if asset not in best or float(s.get("score") or 0) > float(best[asset].get("score") or 0):
                best[asset] = s
        return list(best.values())

    def rank_and_release(self, signals: List[Signal]) -> Dict[str, List[Signal]]:
        # Minimal tier split (kept for tests)
        if self._kill_switch_enabled:
            return {"vip": [], "premium": [], "free": []}

        vip: List[Signal] = []
        premium: List[Signal] = []
        free: List[Signal] = []
        for s in signals:
            score = float(s.get("score") or 0)
            if score >= self.VIP_THRESHOLD:
                vip.append(s)
            elif score >= self.PREMIUM_THRESHOLD:
                premium.append(s)
            else:
                free.append(s)
        return {"vip": vip, "premium": premium, "free": free}

    def is_drawdown(self) -> bool:
        return False

    def generate_watermark(self, signal: Signal) -> str:
        return f"WM{hash(str(signal)) % 10000}"

    def session_active(self, signal: Signal) -> bool:
        return True

    def approve_signals(self, strategy_signals: List[Signal], regime: Optional[str]) -> List[Signal]:
        # Legacy wrapper: returns only approved list
        return self.approve(strategy_signals, regime).approved

    def approve(self, candidates: Iterable[Signal], regime: Optional[str] = None) -> ControllerDecision:
        """Approve candidate signals.

        Enforces:
        - Consensus: >= 3 strategies
        - Group coverage: (Trend or Structure) + Momentum + (Volatility or Volume)
        - HTF alignment hook (placeholder): allowed only if aligned
        - Scoring + thresholds (0-100)
        """

        if self._kill_switch_enabled:
            return ControllerDecision(approved=[], discarded=list(candidates))

        normalized = [self._normalize_signal(s) for s in candidates if s]
        normalized = self._dedupe(normalized)

        approved: List[Signal] = []
        discarded: List[Signal] = []

        for signal in normalized:
            if not self._passes_consensus(signal):
                discarded.append(signal)
                continue

            if not self._passes_htf_alignment(signal):
                discarded.append(signal)
                continue

            risk_profile = calculate_dynamic_risk(signal, regime)
            score = calculate_signal_score(signal, risk_profile, regime)
            signal["score"] = score
            signal["risk_profile"] = risk_profile

            if score < self.PREMIUM_THRESHOLD:
                discarded.append(signal)
                continue

            signal["tier_candidate"] = "vip" if score >= self.VIP_THRESHOLD else "premium"
            approved.append(signal)

        return ControllerDecision(approved=approved, discarded=discarded)

    # --- Legacy helpers (older engine paths) ---
    def can_emit(self, signal: Signal) -> bool:
        if self._kill_switch_enabled:
            return False
        s = self._normalize_signal(signal)
        key = (str(s.get("asset")), str(s.get("timeframe")), str(s.get("direction")))
        return key not in self._cycle_seen

    def register(self, signal: Signal) -> None:
        s = self._normalize_signal(signal)
        key = (str(s.get("asset")), str(s.get("timeframe")), str(s.get("direction")))
        self._cycle_seen.add(key)

    def reset_cycle(self) -> None:
        self._cycle_seen.clear()

    def _normalize_signal(self, s: Signal) -> Signal:
        out = dict(s)
        out.setdefault("signal_id", str(uuid4()))
        out.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        # Normalize key names expected downstream
        if "symbol" in out and "asset" not in out:
            out["asset"] = out["symbol"]
        if "asset" in out and "symbol" not in out:
            out["symbol"] = out["asset"]

        if "stop" in out and "stop_loss" not in out:
            out["stop_loss"] = out["stop"]

        if "targets" in out and "take_profit" not in out:
            out["take_profit"] = out["targets"]

        out.setdefault("strategy_group", (out.get("strategy_group") or "unknown").lower())
        out.setdefault("strategy_name", out.get("strategy") or out.get("strategy_name") or "unknown")

        if "strength" not in out:
            out["strength"] = float(out.get("confidence", 0) or 0)

        direction = (out.get("direction") or "").lower().strip()
        if direction in {"buy", "long"}:
            out["direction"] = "long"
        elif direction in {"sell", "short"}:
            out["direction"] = "short"

        # Compute rr_ratio if possible
        if "rr_ratio" not in out:
            entry = out.get("entry")
            sl = out.get("stop_loss")
            tp = out.get("take_profit")
            try:
                if entry is not None and sl is not None and tp is not None and float(entry) != float(sl):
                    out["rr_ratio"] = abs(float(tp) - float(entry)) / abs(float(entry) - float(sl))
            except Exception:
                pass
        out.setdefault("rr_ratio", 0)

        return out

    def _dedupe(self, signals: List[Signal]) -> List[Signal]:
        seen: Set[Tuple[str, str, str]] = set()
        out: List[Signal] = []
        for s in signals:
            key = (str(s.get("asset")), str(s.get("timeframe")), str(s.get("direction")))
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out

    def _passes_consensus(self, signal: Signal) -> bool:
        """Consensus rules.

        Input format note: If an upstream aggregator merges multiple strategies into
        one candidate, it should provide:
          - contributors: list[str]
          - contributor_groups: list[str]
        Otherwise, we treat single-strategy signals as non-consensus.
        """

        contributors = signal.get("contributors")
        groups = signal.get("contributor_groups")
        if not isinstance(contributors, list) or len(contributors) < 3:
            return False
        if not isinstance(groups, list):
            return False

        groups_norm = {str(g).lower() for g in groups}
        has_momentum = "momentum" in groups_norm
        has_trend_or_structure = bool({"trend", "structure"} & groups_norm)
        has_vol_or_volume = bool({"volatility", "volume"} & groups_norm)
        return has_momentum and has_trend_or_structure and has_vol_or_volume

    def _passes_htf_alignment(self, signal: Signal) -> bool:
        """HTF alignment hook.

        For now, accept if not explicitly marked misaligned.
        Upstream MTF bias filter can set `htf_aligned=False`.
        """

        htf_aligned = signal.get("htf_aligned")
        if htf_aligned is False:
            return False
        return True
