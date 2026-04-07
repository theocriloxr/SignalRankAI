from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from uuid import uuid4
import json
import os
import urllib.request
import urllib.error
import threading

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
    _gemini_daily_limit: int = 10
    _gemini_call_count: int = 0
    _gemini_call_day: str = ""
    _gemini_counter_lock = threading.Lock()

    def __init__(self) -> None:
        self._kill_switch_enabled: bool = False
        self.KILL_SWITCH: Dict[str, Any] = {"enabled": False, "reason": ""}

        # Legacy per-cycle dedupe support (used by older pipeline code)
        self._cycle_seen: Set[Tuple[str, str, str]] = set()

        # Minimal audit logger (kept for existing code/tests)
        # Default to stdout so Railway captures logs, and avoid writing tracked files.
        import logging
        import os

        self.audit_logger = logging.getLogger("audit")
        self.audit_logger.setLevel(logging.INFO)

        if not self.audit_logger.handlers:
            log_path = (os.getenv("AUDIT_LOG_FILE") or "").strip()
            if log_path:
                handler: logging.Handler = logging.FileHandler(log_path)
            else:
                handler = logging.StreamHandler()
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

    def normalize_signals(self, signals: List[Signal]) -> List[Signal]:
        """Normalize signals without deduping.

        This keeps all strategy candidates so consensus can aggregate them.
        """
        return [self._normalize_signal(s) for s in (signals or []) if s]

    def pick_best_direction_per_pair(self, signals: List[Signal]) -> List[Signal]:
        """For each (asset,timeframe), pick the direction (long/short) with higher aggregated confidence.

        Groups by (asset, timeframe) and picks the winning direction (long vs short).
        Returns the best signal for each (asset, timeframe) pair.
        Different pairs are independent - each gets its own best direction.

        Also considers ML probability scores when available. ML-approved signals get a boost.

        Returns one representative signal per (asset, timeframe) pair, with the winning direction.
        """
        grouped: Dict[Tuple[str, str], List[Signal]] = {}
        for s in (signals or []):
            asset = str(s.get("asset") or s.get("symbol") or "").upper().strip()
            tf = str(s.get("timeframe") or "").lower().strip()
            direction = str(s.get("direction") or "").lower().strip()
            if not asset or not tf or direction not in {"long", "short"}:
                continue
            grouped.setdefault((asset, tf), []).append(s)

        def _conf(sig: Signal) -> float:
            """Calculate confidence with ML boost."""
            try:
                conf = sig.get("confidence")
                if conf is None:
                    conf = sig.get("strength")
                w = sig.get("weight")
                if w is None:
                    w = 1.0
                
                base_conf = float(conf or 0.0) * float(w or 1.0)
                
                # Apply ML probability as a multiplier if available
                ml_prob = sig.get("ml_probability")
                if ml_prob is not None:
                    try:
                        ml_prob_val = float(ml_prob)
                        # ML confidence ranges 0-1; scale to multiply base confidence
                        # E.g., ML of 0.7 boosts by 20%, ML of 0.5 reduces by 20%
                        ml_factor = 0.5 + ml_prob_val  # Range [0.5, 1.5]
                        base_conf = base_conf * ml_factor
                    except Exception:
                        pass
                
                return base_conf
            except Exception:
                return 0.0

        out: List[Signal] = []

        def _roi(sig: Signal) -> float:
            try:
                entry = float(sig.get("entry") or 0.0)
                stop_loss = float(sig.get("stop_loss") or sig.get("stop") or 0.0)
                take_profit = sig.get("take_profit")
                if isinstance(take_profit, list) and take_profit:
                    tp = float((take_profit[0] or {}).get("price") or take_profit[0])
                else:
                    tp = float(take_profit or 0.0)
                risk = abs(entry - stop_loss)
                reward = abs(tp - entry)
                if risk <= 0:
                    return 0.0
                return reward / risk
            except Exception:
                return 0.0

        def _composite(sig: Signal) -> float:
            try:
                risk = max(0.0001, float(sig.get("risk", 1.0) or 1.0))
            except Exception:
                risk = 1.0
            return (_conf(sig) * 0.6) + (_roi(sig) * 30.0) - (risk * 10.0)

        def _can_call_gemini() -> tuple[bool, str]:
            api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
            if not api_key:
                return False, "missing_api_key"
            try:
                self._gemini_daily_limit = max(1, int(os.getenv("GEMINI_DAILY_LIMIT", "10") or 10))
            except Exception:
                self._gemini_daily_limit = 10
            today = datetime.utcnow().strftime("%Y-%m-%d")
            with self._gemini_counter_lock:
                if self._gemini_call_day != today:
                    self._gemini_call_day = today
                    self._gemini_call_count = 0
                if self._gemini_call_count >= self._gemini_daily_limit:
                    return False, "daily_limit_reached"
                return True, "ok"

        def _gemini_pick(asset: str, tf: str, longs: List[Signal], shorts: List[Signal]) -> tuple[str | None, str]:
            can_call, reason = _can_call_gemini()
            if not can_call:
                self.audit_logger.debug("gemini_inline skipped asset=%s tf=%s reason=%s", asset, tf, reason)
                return None, reason
            api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
            model = (os.getenv("GEMINI_INLINE_MODEL") or "gemini-1.5-flash").strip()
            prompt = {
                "asset": asset,
                "timeframe": tf,
                "long_candidates": longs[:5],
                "short_candidates": shorts[:5],
                "goal": "Pick direction with highest chance of success, highest ROI, lowest risk. Return JSON {\"winner\":\"long|short\"}",
            }
            body = json.dumps({
                "contents": [{"parts": [{"text": json.dumps(prompt)}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 200},
            }).encode("utf-8")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            try:
                timeout_s = max(2, int(os.getenv("GEMINI_API_TIMEOUT_SECONDS", "8") or 8))
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                with self._gemini_counter_lock:
                    self._gemini_call_count += 1
                txt = raw.lower()
                if '"winner":"short"' in txt or "winner short" in txt:
                    return "short", "ok"
                if '"winner":"long"' in txt or "winner long" in txt:
                    return "long", "ok"
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, Exception) as exc:
                self.audit_logger.debug("gemini_inline failed asset=%s tf=%s error=%s", asset, tf, exc)
                return None, "request_failed"
            return None, "unparseable_response"

        try:
            gemini_top_n = max(1, int(os.getenv("GEMINI_INLINE_TOP_N", "3") or 3))
        except Exception:
            gemini_top_n = 3
        gemini_shortlist: Set[Tuple[str, str]] = set()
        conflict_pairs: List[Tuple[float, str, str]] = []
        for (asset, tf), items in grouped.items():
            longs = [s for s in items if str(s.get("direction")).lower() == "long"]
            shorts = [s for s in items if str(s.get("direction")).lower() == "short"]
            if not (longs and shorts):
                continue
            long_sum = sum(_conf(s) for s in longs)
            short_sum = sum(_conf(s) for s in shorts)
            total = abs(long_sum) + abs(short_sum)
            margin = abs(long_sum - short_sum) / (total + 1e-9)
            conflict_pairs.append((margin, asset, tf))
        conflict_pairs.sort(key=lambda x: x[0])
        gemini_shortlist = {(asset, tf) for _, asset, tf in conflict_pairs[:gemini_top_n]}

        for (asset, tf), items in grouped.items():
            longs = [s for s in items if str(s.get("direction")).lower() == "long"]
            shorts = [s for s in items if str(s.get("direction")).lower() == "short"]

            long_sum = sum(_conf(s) for s in longs)
            short_sum = sum(_conf(s) for s in shorts)

            if long_sum == 0 and short_sum == 0:
                continue

            winning_side = None
            gemini_reason = "not_applicable"
            if longs and shorts:
                if (asset, tf) in gemini_shortlist:
                    gemini_winner, gemini_reason = _gemini_pick(asset, tf, longs, shorts)
                else:
                    gemini_winner, gemini_reason = (None, "not_shortlisted")
                if gemini_winner == "long":
                    winning_side = "long"
                elif gemini_winner == "short":
                    winning_side = "short"
                else:
                    long_best = max((_composite(s) for s in longs), default=0.0)
                    short_best = max((_composite(s) for s in shorts), default=0.0)
                    winning_side = "long" if long_best >= short_best else "short"
            else:
                winning_side = "long" if long_sum >= short_sum else "short"

            # Pick the direction with higher quality for THIS pair only
            winning = longs if winning_side == "long" else shorts
            if not winning:
                continue

            # Pick the best signal from the winning direction
            winning_sorted = sorted(winning, key=_conf, reverse=True)
            best = dict(winning_sorted[0])

            # Add contributor metadata for debugging/analysis
            try:
                best["contributors"] = [str(s.get("strategy_name") or s.get("strategy") or "").strip() for s in winning if (s.get("strategy_name") or s.get("strategy"))]
                best["contributor_groups"] = [str(s.get("strategy_group") or "").strip().lower() for s in winning if s.get("strategy_group")]
                best["direction_score_long"] = float(long_sum)
                best["direction_score_short"] = float(short_sum)
                best["num_strategies"] = len(winning)
                # Track ML voting if signals have ML scores
                if any(s.get("ml_probability") for s in winning):
                    best["ml_voted"] = True
                    winning_ml_probs = [s.get("ml_probability") for s in winning if s.get("ml_probability") is not None]
                    if winning_ml_probs:
                        best["winning_avg_ml_prob"] = sum(winning_ml_probs) / len(winning_ml_probs)
                best["gemini_inline_reason"] = str(gemini_reason)
                best["gemini_inline_used"] = bool(gemini_reason == "ok")
            except Exception:
                pass

            out.append(best)

        return out

    def cap_correlation(self, signals: List[Signal]) -> List[Signal]:
        # Correlation cap: one per asset (highest score wins)
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
        - HTF alignment hook: allowed only if aligned
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
        entry = out.get("entry")
        tp = out.get("take_profit")
        # Infer direction if missing or invalid
        if direction in {"buy", "long"}:
            out["direction"] = "long"
        elif direction in {"sell", "short"}:
            out["direction"] = "short"
        else:
            try:
                entry_f = float(entry) if entry is not None else None
                # Handle TP as list or float
                if isinstance(tp, (list, tuple)) and tp:
                    tp_f = float(tp[0])
                else:
                    tp_f = float(tp) if tp is not None else None
                if entry_f is not None and tp_f is not None:
                    if tp_f < entry_f:
                        out["direction"] = "short"
                    elif tp_f > entry_f:
                        out["direction"] = "long"
            except Exception:
                pass

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
