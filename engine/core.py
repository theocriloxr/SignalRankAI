import os
import time
import asyncio

from data.fetcher import is_crypto, is_binance_blocked, market_closed_reason
from data.market_data import fetch_market_data_cached
from data.pair_discovery import get_all_trending_pairs
from engine.regime import detect_market_regime
from strategies import run_all_strategies
from engine.consensus import apply_consensus_filter
from engine.risk import calculate_dynamic_risk
from engine.scoring import calculate_signal_score
from db.pg_compat import get_all_user_ids_compat, store_signal_compat
from engine.ranking import rank_signals
from signalrank_telegram.bot import dispatch_signals
from core.redis_state import state


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


# Store/dispatch threshold for the main pipeline.
# Higher = fewer signals but higher quality. Lower = more signals but more noise.
# Balanced at 55 for good quality with reasonable signal volume
# Range: 40-75 recommended.
# - 40: Very permissive (all passing signals, more noise)
# - 55: Balanced (good quality with reasonable volume) - DEFAULT
# - 60: Selective (premium signals only)
# - 70: Strict (only top tier signals)
MIN_SCORE_THRESHOLD = _env_float("PREMIUM_SCORE_THRESHOLD", 55)

def load_tradable_assets():
    """Return configured fallback assets.

    This intentionally avoids hardcoded demo symbols.
    Use TRADABLE_ASSETS="BTCUSDT,ETHUSDT" (comma-separated) to provide a fallback list.
    """
    raw = (os.getenv("TRADABLE_ASSETS") or "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    raw = raw.strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _short_err(e: Exception, limit: int = 180) -> str:
    try:
        s = f"{type(e).__name__}: {e}"
    except Exception:
        s = "Exception"
    s = (s or "").replace("\n", " ").replace("\r", " ").strip()
    if len(s) > int(limit):
        return s[: int(limit) - 3] + "..."
    return s


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        xs = str(x or "").strip()
        if not xs or xs in seen:
            continue
        seen.add(xs)
        out.append(xs)
    return out


def _rotate_slice(items: list[str], start: int, size: int) -> list[str]:
    if size <= 0:
        return []
    if len(items) <= size:
        return list(items)
    n = len(items)
    s = int(start) % n
    e = s + int(size)
    if e <= n:
        return items[s:e]
    return items[s:] + items[: (e - n)]


async def _fetch_market_data_for_assets(asset_to_timeframes: dict[str, list[str]]) -> dict[str, dict]:
    """Fetch cached market data for many assets using a bounded concurrency."""

    concurrency = max(1, _env_int("MARKET_CACHE_FETCH_CONCURRENCY", 8))
    per_asset_timeout = float(_env_float("MARKET_FETCH_TIMEOUT_SECONDS", 25.0))
    sem = asyncio.Semaphore(concurrency)

    async def _one(asset: str, tfs: list[str]) -> tuple[str, dict]:
        async with sem:
            try:
                data = await asyncio.wait_for(fetch_market_data_cached(asset, tfs), timeout=max(1.0, per_asset_timeout))
                return asset, (data or {})
            except asyncio.TimeoutError:
                return asset, {}
            except Exception:
                return asset, {}

    tasks = [_one(a, tfs) for a, tfs in (asset_to_timeframes or {}).items()]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return {asset: data for asset, data in results}

def main_loop(DRY_RUN=False):
    crypto_timeframes = [x.strip() for x in (os.getenv("CRYPTO_TIMEFRAMES") or "5m,15m,1h,4h,1d").split(",") if x.strip()]
    # AlphaVantage free tier is rate-limited; default to daily-only for FX.
    fx_timeframes = [x.strip() for x in (os.getenv("FX_TIMEFRAMES") or "1d").split(",") if x.strip()]

    if _env_bool("ENGINE_CYCLE_LOG", True):
        try:
            print(
                "[engine] loop_start "
                f"dry_run={bool(DRY_RUN)} "
                f"cycle_sleep_seconds={int(os.getenv('CYCLE_SLEEP_SECONDS', '60'))} "
                f"crypto_timeframes={','.join(crypto_timeframes)} "
                f"fx_timeframes={','.join(fx_timeframes)}",
                flush=True,
            )
        except Exception:
            pass

    try:
        fx_max_pairs = int((os.getenv("FX_MAX_PAIRS_PER_CYCLE") or os.getenv("FX_MAX_PAIRS") or "6").strip())
    except Exception:
        fx_max_pairs = 6

    cycle_sleep_seconds = int(os.getenv("CYCLE_SLEEP_SECONDS", "60"))

    # If FX pairs are configured, require a real candle provider key.
    # Non-fatal: warn and disable FX rather than crashing the whole engine.
    fx_pairs = (os.getenv("FX_PAIRS") or "").strip()
    fx_enabled = True
    if not (os.getenv("ALPHAVANTAGE_API_KEY") or "").strip():
        # If we don't have a provider key, we can still run crypto-only.
        # FX pairs (configured or defaulted) will be skipped below.
        fx_enabled = False
        if fx_pairs:
            print(
                "[WARN] FX_PAIRS is set but ALPHAVANTAGE_API_KEY is missing. Disabling FX candles.",
                flush=True,
            )

    # Example: fetch strategy weights and regime_strategies from ML/DB (stubbed here)
    from engine.ml import get_strategy_weights, get_regime_strategies
    strategy_weights = get_strategy_weights() if hasattr(get_strategy_weights, '__call__') else {}
    regime_strategies = get_regime_strategies() if hasattr(get_regime_strategies, '__call__') else None

    while True:
        # Increment cycle counter early so we can use it for pair rotation.
        try:
            cycle_no = _env_int("_ENGINE_CYCLE_NO", 0) + 1
            os.environ["_ENGINE_CYCLE_NO"] = str(cycle_no)
        except Exception:
            cycle_no = 0

        if _env_bool("ENGINE_CYCLE_LOG", True):
            try:
                every = max(1, _env_int("ENGINE_CYCLE_LOG_EVERY", 1))
                if cycle_no <= 0 or (cycle_no % every) == 0:
                    print(f"[engine] cycle={cycle_no} start", flush=True)
            except Exception:
                pass

        cycle_assets = 0
        cycle_candidates = 0
        cycle_after_dedupe = 0
        cycle_after_consensus = 0
        cycle_after_risk = 0
        cycle_after_ml = 0
        cycle_scored = 0
        cycle_stored = 0
        cycle_store_failures = 0
        cycle_store_error = None
        cycle_max_score = None
        cycle_max_score_asset = None
        cycle_users = 0
        cycle_dispatched_users = 0
        # Global kill-switch (skip cycle but keep process alive)
        try:
            if state.get_killswitch_sync().enabled:
                if _env_bool("ENGINE_CYCLE_LOG", True):
                    try:
                        print(f"[engine] cycle={cycle_no} skipped=killswitch", flush=True)
                    except Exception:
                        pass
                time.sleep(max(5, cycle_sleep_seconds))
                continue
        except Exception:
            pass

        try:
            # Prioritize TRADABLE_ASSETS env for crypto; fallback to discovery if empty.
            tradable = load_tradable_assets()
            try:
                discovered = get_all_trending_pairs() or []
            except Exception:
                discovered = []

            if tradable:
                assets = tradable  # Env-configured universe takes priority
            else:
                assets = discovered  # Fallback to discovery

            if _env_bool("ENGINE_CYCLE_LOG", True) and _env_bool("ENGINE_ASSET_DEBUG", False):
                try:
                    raw_tradable = (os.getenv("TRADABLE_ASSETS") or "").strip()
                    raw_fx = (os.getenv("FX_PAIRS") or "").strip()
                    print(
                        f"[engine] env tradable_len={len(raw_tradable)} fx_len={len(raw_fx)} tradable_count={len(tradable)} discovered_count={len(discovered)} final_count={len(assets)}",
                        flush=True,
                    )
                except Exception:
                    pass

            # No assets => do not run on demo/hardcoded data.
            if not assets:
                if _env_bool("ENGINE_CYCLE_LOG", True):
                    try:
                        print(f"[engine] cycle={cycle_no} skipped=no_assets", flush=True)
                    except Exception:
                        pass
                time.sleep(max(5, cycle_sleep_seconds))
                continue

            # Cap FX pairs per cycle to avoid AlphaVantage throttling (especially on free tier).
            try:
                assets = _dedupe_preserve_order(list(assets or []))

                # Filter out closed markets with per-pair notice.
                closed_notes = []
                open_assets = []
                for a in assets:
                    reason = market_closed_reason(a)
                    if reason:
                        closed_notes.append((a, reason))
                    else:
                        open_assets.append(a)
                if closed_notes and _env_bool("ENGINE_CYCLE_LOG", True):
                    try:
                        msg = ", ".join([f"{p}:{r}" for p, r in closed_notes])
                        print(f"[engine] cycle={cycle_no} market_closed skip={msg}", flush=True)
                    except Exception:
                        pass

                fx_assets = [a for a in open_assets if not is_crypto(a)]
                crypto_assets = [a for a in open_assets if is_crypto(a)]
                if not fx_enabled:
                    fx_assets = []

                # FX universe can be moderate; bound per-cycle calls but rotate to cover all.
                fx_pair_rotation = _env_bool("FX_PAIR_ROTATION", True)
                if fx_assets and fx_max_pairs > 0 and len(fx_assets) > int(fx_max_pairs):
                    if fx_pair_rotation:
                        start = (max(0, int(cycle_no)) - 1) * int(fx_max_pairs)
                        fx_assets = _rotate_slice(fx_assets, start=start, size=int(fx_max_pairs))
                    else:
                        fx_assets = fx_assets[: int(fx_max_pairs)]

                # Crypto universe can be large; bound per-cycle work but rotate so we cover all.
                default_crypto_max = 20
                try:
                    # If Binance is blocked and we don't have a CryptoCompare key,
                    # calling CryptoCompare too aggressively can yield empty candles.
                    if is_binance_blocked() and not (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip():
                        default_crypto_max = 8
                except Exception:
                    pass
                crypto_max_pairs = _env_int("CRYPTO_MAX_PAIRS_PER_CYCLE", int(default_crypto_max))
                crypto_pair_rotation = _env_bool("CRYPTO_PAIR_ROTATION", True)
                if crypto_max_pairs > 0 and len(crypto_assets) > crypto_max_pairs:
                    if crypto_pair_rotation:
                        start = (max(0, int(cycle_no)) - 1) * int(crypto_max_pairs)
                        crypto_assets = _rotate_slice(crypto_assets, start=start, size=int(crypto_max_pairs))
                    else:
                        crypto_assets = crypto_assets[: int(crypto_max_pairs)]

                assets = crypto_assets + fx_assets
            except Exception:
                pass

            cycle_assets = len(assets)

            # Optional visibility into what we are actually scanning.
            if _env_bool("ENGINE_CYCLE_LOG", True) and _env_bool("ENGINE_ASSET_DEBUG", False):
                try:
                    crypto_n = len([a for a in assets if is_crypto(a)])
                    fx_n = len([a for a in assets if not is_crypto(a)])
                    sample = ",".join([str(a) for a in list(assets)[:10]])
                    print(
                        f"[engine] cycle={cycle_no} assets_split crypto={crypto_n} fx={fx_n} sample={sample}",
                        flush=True,
                    )
                except Exception:
                    pass

            scored_signals_all = []

            # Fetch all market data once per cycle (avoids per-asset asyncio.run overhead).
            asset_to_tfs: dict[str, list[str]] = {}
            for asset in assets:
                tfs = crypto_timeframes if is_crypto(asset) else fx_timeframes
                asset_to_tfs[str(asset)] = list(tfs)

            try:
                all_market_data = asyncio.run(_fetch_market_data_for_assets(asset_to_tfs))
            except Exception:
                all_market_data = {}

            for asset in assets:
                try:
                    market_data = (all_market_data or {}).get(asset) or {}

                    # Fail-closed: never run strategies on empty/insufficient market data.
                    try:
                        min_candles = int((os.getenv("MIN_CANDLES_PER_TIMEFRAME") or "50").strip())
                    except Exception:
                        min_candles = 50
                    min_candles = max(1, int(min_candles))
                    if not market_data:
                        continue
                    has_enough = False
                    for tf_data in (market_data or {}).values():
                        candles = (tf_data or {}).get("candles") or []
                        if isinstance(candles, list) and len(candles) >= min_candles:
                            has_enough = True
                            break
                    if not has_enough:
                        continue

                    regime = detect_market_regime(market_data)
                    strategy_signals = run_all_strategies(
                        asset,
                        market_data,
                        regime,
                        strategy_weights=strategy_weights,
                        regime_strategies=regime_strategies,
                    )

                    try:
                        cycle_candidates += len(strategy_signals or [])
                    except Exception:
                        pass

                    # Signal Controller step (deduplication + normalization)
                    from engine.signal_controller import SignalController

                    controller = SignalController()
                    normalized_signals = controller.normalize_signals(strategy_signals)

                    # Consensus Engine (aggregates across strategies)
                    from engine.consensus import consensus_filter
                    consensus_signals = consensus_filter(normalized_signals)

                    # Per pair/timeframe, pick the stronger direction (buy vs sell)
                    selected_signals = controller.pick_best_direction_per_pair(consensus_signals)
                    try:
                        cycle_after_consensus += len(consensus_signals or [])
                    except Exception:
                        pass
                    try:
                        cycle_after_dedupe += len(selected_signals or [])
                    except Exception:
                        pass

                    # Risk Engine
                    from engine.risk import risk_check

                    account_state = type('AccountState', (), {'drawdown': 0.0})()  # Replace with real account state
                    risk_signals = [s for s in selected_signals if risk_check(s, account_state)]
                    try:
                        cycle_after_risk += len(risk_signals or [])
                    except Exception:
                        pass

                    # ML Probability Filter
                    from ml.features import extract_features
                    from ml.inference import MLFilter

                    ml_filter = MLFilter()
                    ml_signals = []
                    try:
                        ml_threshold = float((os.getenv("ML_PROB_THRESHOLD") or "0.6").strip())
                    except Exception:
                        ml_threshold = 0.6
                    for signal in risk_signals:
                        if getattr(ml_filter, "active", False):
                            features = extract_features(signal, market_data)
                            try:
                                approved, probability = ml_filter.ml_filter(features, threshold=ml_threshold)
                            except Exception:
                                approved, probability = True, None
                        else:
                            approved, probability = True, None
                        if not approved:
                            continue
                        signal["ml_probability"] = probability
                        ml_signals.append(signal)
                    try:
                        cycle_after_ml += len(ml_signals or [])
                    except Exception:
                        pass

                    # Scoring
                    from engine.scoring import score_signal

                    for signal in ml_signals:
                        score = score_signal(signal)
                        signal['score'] = score
                        try:
                            if cycle_max_score is None or float(score) > float(cycle_max_score):
                                cycle_max_score = float(score)
                                cycle_max_score_asset = str(signal.get('asset') or signal.get('symbol') or '')
                        except Exception:
                            pass
                        if score >= MIN_SCORE_THRESHOLD:
                            # Normalize for DB + formatters
                            signal['regime'] = regime
                            signal['stop_loss'] = signal.get('stop_loss', signal.get('stop'))
                            signal['take_profit'] = signal.get('take_profit', signal.get('targets'))
                            entry = signal.get('entry')
                            sl = signal.get('stop_loss')
                            tp = signal.get('take_profit')
                            if entry is not None and sl is not None and tp is not None and abs(entry - sl) > 0:
                                signal['rr_ratio'] = abs(tp - entry) / abs(entry - sl)
                            else:
                                signal['rr_ratio'] = signal.get('rr_ratio', 0)
                            scored_signals_all.append(signal)
                            cycle_scored += 1
                            try:
                                store_signal_compat(signal)
                                cycle_stored += 1
                            except Exception as e:
                                cycle_store_failures += 1
                                # Keep loop alive but emit a single useful hint per cycle.
                                if cycle_store_failures == 1:
                                    cycle_store_error = _short_err(e)
                                    try:
                                        print(f"[ERROR] store_signal failed: {type(e).__name__}: {e}", flush=True)
                                    except Exception:
                                        pass

                                    # Optional traceback for faster diagnosis in production logs.
                                    if _env_bool("STORE_SIGNAL_TRACE", False):
                                        try:
                                            import traceback

                                            traceback.print_exc()
                                        except Exception:
                                            pass
                except Exception:
                    # Isolate per-asset failures so the loop stays alive.
                    continue

            # Ranking and Dispatch
            ranked_signals = rank_signals(scored_signals_all)
            if DRY_RUN:
                for sig in (ranked_signals.get('vip', []) + ranked_signals.get('premium', [])):
                    print("[DRY RUN]", sig)
            else:
                user_ids = get_all_user_ids_compat()
                try:
                    cycle_users = len(user_ids or [])
                except Exception:
                    cycle_users = 0
                for user_id in user_ids:
                    dispatch_signals(ranked_signals, user_id=user_id)
                    cycle_dispatched_users += 1

            # One-line per-cycle health signal for Railway logs.
            if _env_bool("ENGINE_CYCLE_LOG", True):
                every = max(1, _env_int("ENGINE_CYCLE_LOG_EVERY", 1))
                if cycle_no <= 0 or (cycle_no % every) == 0:
                    crypto_provider = (os.getenv("CRYPTO_DATA_PROVIDER") or "binance").strip().lower()
                    print(
                        "[engine] cycle="
                        f"{cycle_no} assets={cycle_assets} candidates={cycle_candidates} "
                            f"deduped={cycle_after_dedupe} consensus={cycle_after_consensus} risk_ok={cycle_after_risk} ml_ok={cycle_after_ml} "
                        f"scored>={MIN_SCORE_THRESHOLD:.2f}={cycle_scored} stored={cycle_stored} "
                        f"store_failures={cycle_store_failures} "
                            f"store_error={cycle_store_error or 'n/a'} "
                        f"users={cycle_users} dispatched={cycle_dispatched_users} "
                            f"max_score={cycle_max_score if cycle_max_score is not None else 'n/a'} max_score_asset={cycle_max_score_asset or 'n/a'} "
                            f"crypto_provider={crypto_provider} fx_enabled={fx_enabled}",
                        flush=True,
                    )
        except Exception:
            # Keep process alive; production version should log structured errors.
            if _env_bool("ENGINE_CYCLE_LOG", True):
                try:
                    import traceback

                    print(f"[engine] cycle={cycle_no} error=unhandled_exception", flush=True)
                    traceback.print_exc()
                except Exception:
                    pass

        time.sleep(max(5, cycle_sleep_seconds))
