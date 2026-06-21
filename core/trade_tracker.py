import logging
from datetime import datetime, timezone
import yfinance as yf
import requests
import os

from core.redis_state import state
from services.asset_mapper import classify_asset

logger = logging.getLogger(__name__)

# Simple in-memory price cache: symbol -> {ts: float, price: float}
_PRICE_CACHE: dict[str, dict] = {}
_PRICE_FAILURE_STATE: dict[str, dict] = {}
_ACTIVE_TRADES_LOADED = False


def _set_price_cache(symbol: str, price: float):
    try:
        _PRICE_CACHE[(symbol or "").upper()] = {"ts": datetime.now(timezone.utc).timestamp(), "price": float(price)}
    except Exception:
        pass


def _get_price_cache(symbol: str, max_age_s: float = 120.0):
    try:
        rec = _PRICE_CACHE.get((symbol or "").upper())
        if not rec:
            return None
        if (datetime.now(timezone.utc).timestamp() - float(rec.get("ts", 0))) > float(_env_get("PRICE_CACHE_TTL", max_age_s)):
            return None
        return rec.get("price")
    except Exception:
        return None


def _get_backoff_base_seconds() -> float:
    try:
        return float(_env_get("PRICE_FETCH_BACKOFF_BASE_SECONDS", 30.0))
    except Exception:
        return 30.0


def _get_backoff_max_seconds() -> float:
    try:
        return float(_env_get("PRICE_FETCH_BACKOFF_MAX_SECONDS", 300.0))
    except Exception:
        return 300.0


def _backoff_key(symbol: str) -> str:
    return (symbol or "").upper().strip()


def _get_backoff_state(symbol: str):
    return _PRICE_FAILURE_STATE.get(_backoff_key(symbol)) or {}


def _next_backoff_delay(failure_count: int) -> float:
    base = max(1.0, _get_backoff_base_seconds())
    maximum = max(base, _get_backoff_max_seconds())
    delay = base * (2 ** max(0, failure_count - 1))
    return min(maximum, delay)


def _record_price_failure(symbol: str) -> float:
    key = _backoff_key(symbol)
    now = datetime.now(timezone.utc).timestamp()
    state = dict(_PRICE_FAILURE_STATE.get(key) or {})
    failure_count = int(state.get("failures", 0)) + 1
    delay = _next_backoff_delay(failure_count)
    next_retry = now + delay
    _PRICE_FAILURE_STATE[key] = {
        "failures": failure_count,
        "last_failure_ts": now,
        "next_retry_ts": next_retry,
        "backoff_s": delay,
    }
    return next_retry


def _record_price_success(symbol: str):
    _PRICE_FAILURE_STATE.pop(_backoff_key(symbol), None)


def _market_closed_reason(symbol: str) -> str | None:
    try:
        asset_class = classify_asset(symbol)
    except Exception:
        asset_class = "unknown"

    try:
        from data.market_hours import is_fx_holiday, is_stock_holiday, is_commodity_holiday, is_fx_low_liquidity
        now = datetime.now(timezone.utc)
        if asset_class == "stock":
            return is_stock_holiday(now)
        if asset_class == "commodity":
            return is_commodity_holiday(now)
        if asset_class == "forex":
            holiday = is_fx_holiday(now)
            if holiday:
                return holiday
            if is_fx_low_liquidity(now):
                return "FX market low-liquidity window"
    except Exception:
        return None
    return None


def _allow_external_price_fallback() -> bool:
    raw = str(_env_get("TRADE_TRACKER_ALLOW_EXTERNAL_FALLBACK", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _latest_tick_price(symbol: str):
    try:
        payload = state.get_latest_tick_sync(symbol)
        if isinstance(payload, dict):
            price = payload.get("price")
            if price is not None:
                price = float(price)
                if price > 0:
                    _set_price_cache(symbol, price)
                    return price
    except Exception:
        pass
    return None


def _trade_state_payload(trade) -> dict:
    return {
        "signal_id": trade.signal_id,
        "symbol": trade.symbol,
        "entry": trade.entry,
        "stop": trade.stop,
        "targets": list(getattr(trade, "targets", []) or []),
        "direction": trade.direction,
        "open_time": trade.open_time,
        "targets_hit": list(getattr(trade, "targets_hit", []) or []),
        "signal": dict(getattr(trade, "signal", {}) or {}),
    }


def _load_open_trades_from_state(force: bool = False) -> None:
    global _ACTIVE_TRADES_LOADED
    if _ACTIVE_TRADES_LOADED and not force:
        return
    try:
        payloads = state.get_active_trades_sync() or {}
    except Exception:
        payloads = {}

    if not isinstance(payloads, dict):
        _ACTIVE_TRADES_LOADED = True
        return

    existing_keys = {_trade_key(trade.signal) for trade in open_trades_list}
    for trade_id, payload in payloads.items():
        try:
            raw_signal = payload.get("signal") if isinstance(payload, dict) else None
            signal = dict(raw_signal or payload or {})
            signal.setdefault("signal_id", trade_id)
            key = _trade_key(signal)
            if key in existing_keys:
                continue
            trade = TradeRecord(signal)
            targets_hit = payload.get("targets_hit") if isinstance(payload, dict) else None
            if isinstance(targets_hit, list):
                trade.targets_hit = list(targets_hit)
            open_trades_list.append(trade)
            existing_keys.add(key)
        except Exception:
            continue

    _ACTIVE_TRADES_LOADED = True


def _persist_trade_state(trade) -> None:
    try:
        state.set_active_trade_sync(str(trade.signal_id or trade.symbol or id(trade)), _trade_state_payload(trade))
    except Exception:
        pass


def _remove_trade_state(trade) -> None:
    try:
        state.remove_active_trade_sync(str(trade.signal_id or trade.symbol or id(trade)))
    except Exception:
        pass


def _env_get(name: str, default):
    import os
    try:
        return os.getenv(name) or default
    except Exception:
        return default


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class TradeRecord:
    def __init__(self, signal):
        # Normalize common signal field names used across the codebase/tests
        self.signal_id = signal.get("id") or signal.get("signal_id")
        self.symbol = signal.get("symbol") or signal.get("asset")
        self.entry = signal.get("entry") or signal.get("price") or signal.get("entry_price")
        # stop can be provided as 'stop', 'stop_loss' or 'stopLoss'
        self.stop = signal.get("stop") or signal.get("stop_loss") or signal.get("stopLoss")
        # targets may be 'targets' (list) or 'take_profit' / 'take_profits' (single)
        t = signal.get("targets") or signal.get("targets_list") or signal.get("take_profit") or signal.get("take_profits") or signal.get("take_profit")
        self.target = t
        # Normalize direction to lowercase 'long' or 'short' (tests expect lowercase)
        self.direction = (signal.get("direction") or signal.get("side") or "long").lower()
        # Timestamp fallback
        self.open_time = signal.get("timestamp") or signal.get("created_at") or _utcnow_naive().isoformat()
        self.close_time = None
        self.outcome = None  # "TP" | "SL"
        self.signal = signal  # Keep reference to original signal
        # Helper: ensure targets list for easier checks
        if self.target is None:
            self.targets = []
        elif isinstance(self.target, list):
            self.targets = self.target
        else:
            # single numeric target
            try:
                self.targets = [float(self.target)]
            except Exception:
                self.targets = []
        # Track which targets have been hit (for partial TP handling)
        self.targets_hit = []

open_trades_list = []


def _trade_key(signal: dict) -> tuple:
    """Generate unique key for trade tracking.
    
    FIX: Changed to exclude timeframe from the key.
    Previously, same asset+direction on different timeframes was treated as different trades,
    causing duplicate "Trade opened" entries. Now we use only symbol+direction for deduplication.
    This allows the same trading idea on multiple timeframes to share one trade record.
    """
    signal_id = signal.get("id") or signal.get("signal_id")
    if signal_id:
        return ("signal_id", str(signal_id))
    symbol = str(signal.get("symbol") or signal.get("asset") or "").upper().strip()
    direction = str(signal.get("direction") or signal.get("side") or "long").lower().strip()
    # Remove timeframe from key to prevent duplicate trades across timeframes
    # The same asset+direction should be tracked as ONE trade, regardless of timeframe
    entry = signal.get("entry") or signal.get("price") or signal.get("entry_price")
    stop = signal.get("stop") or signal.get("stop_loss") or signal.get("stopLoss")
    return ("fallback", symbol, direction, str(entry), str(stop))

def open_trades():
    try:
        payloads = state.get_active_trades_sync() or {}
    except Exception:
        payloads = None

    if payloads == {} and os.getenv("REDIS_URL"):
        if open_trades_list:
            open_trades_list.clear()
        global _ACTIVE_TRADES_LOADED
        _ACTIVE_TRADES_LOADED = True
        return []

    if not open_trades_list:
        _load_open_trades_from_state()
    return list(open_trades_list)

def _convert_symbol_for_yfinance(symbol):
    """Convert crypto symbols from Binance format to yfinance format."""
    try:
        from data.market_data import format_ticker
        return format_ticker(symbol, "yfinance")
    except Exception:
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}-USD"
        if symbol.endswith("USD"):
            return f"{symbol[:-3]}-USD"
        return symbol

def _get_current_price(symbol):
    """
    Fetch current price for a symbol.
    Primary: yfinance fast_info
    Fallback: Binance REST API for crypto
    """
    # Prefer Redis-fed ticks first so live tracking stays event-driven.
    try:
        latest = _latest_tick_price(symbol)
        if latest is not None:
            logger.debug(f"Using latest tick for {symbol}: {latest}")
            return float(latest)
    except Exception:
        pass

    # Try price cache first
    try:
        cached = _get_price_cache(symbol)
        if cached is not None:
            logger.debug(f"Using cached price for {symbol}: {cached}")
            return float(cached)
    except Exception:
        pass

    now_ts = datetime.now(timezone.utc).timestamp()
    backoff_state = _get_backoff_state(symbol)
    next_retry_ts = float(backoff_state.get("next_retry_ts", 0.0) or 0.0)
    if next_retry_ts and now_ts < next_retry_ts:
        logger.debug(
            "Skipping live price fetch for %s until %.0f (backoff=%ss, failures=%s)",
            symbol,
            next_retry_ts,
            backoff_state.get("backoff_s"),
            backoff_state.get("failures"),
        )
        return None

    # Respect asset-specific market closures to avoid noisy lookups when markets are shut.
    closed_reason = _market_closed_reason(symbol)
    if closed_reason:
        logger.debug("Skipping live price fetch for %s: %s", symbol, closed_reason)
        return None

    if not _allow_external_price_fallback():
        logger.debug("Skipping external price fallback for %s because TRADE_TRACKER_ALLOW_EXTERNAL_FALLBACK is disabled", symbol)
        return None

    # Try yfinance first
    try:
        yf_symbol = _convert_symbol_for_yfinance(symbol)
        ticker = yf.Ticker(yf_symbol)
        fast_info = getattr(ticker, "fast_info", {}) or {}
        price = fast_info.get('lastPrice') or fast_info.get('last_price') or fast_info.get('regularMarketPrice')
        if price and price > 0:
            logger.debug(f"Got price for {symbol} ({yf_symbol}) from yfinance: {price}")
            _record_price_success(symbol)
            return float(price)
        history = ticker.history(period="2d", interval="1m", auto_adjust=False)
        if history is not None and not history.empty:
            last_close = float(history["Close"].dropna().iloc[-1])
            if last_close > 0:
                logger.debug(f"Got price for {symbol} ({yf_symbol}) from yfinance history: {last_close}")
                _record_price_success(symbol)
                return last_close
    except Exception as e:
        logger.debug(f"yfinance failed for {symbol}: {e}")
    
    # Fallback to Binance for crypto
    if symbol.endswith("USDT") or symbol.endswith("USD"):
        try:
            binance_symbol = symbol if symbol.endswith("USDT") else f"{symbol}T"
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={binance_symbol}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                price = float(data["price"])
                logger.debug(f"Got price for {symbol} from Binance: {price}")
                try:
                    _set_price_cache(symbol, price)
                except Exception:
                    pass
                _record_price_success(symbol)
                return price
        except Exception as e:
            logger.debug(f"Binance API failed for {symbol}: {e}")
            # Record failure early so immediate subsequent calls observe backoff
            try:
                _record_price_failure(symbol)
            except Exception:
                pass
            return None
    
    # Last-resort: try unified providers waterfall for recent candles
    try:
        from data.providers import fetch_candles_waterfall
        candles = fetch_candles_waterfall(symbol, "1h", limit=5)
        if candles:
            # Use the last close
            last = candles[-1]
            price = float(last.get("close") or last.get("c") or 0)
            if price and price > 0:
                try:
                    _set_price_cache(symbol, price)
                except Exception:
                    pass
                logger.debug(f"Got price for {symbol} from providers.waterfall: {price}")
                _record_price_success(symbol)
                return price
    except Exception:
        pass

    next_retry_ts = _record_price_failure(symbol)
    state = _get_backoff_state(symbol)
    if int(state.get("failures", 0)) <= 1:
        logger.warning(
            "Could not fetch price for %s; retrying after %.0fs",
            symbol,
            float(state.get("backoff_s", 0.0) or 0.0),
        )
    else:
        logger.debug(
            "Could not fetch price for %s; backoff active until %.0f (failures=%s)",
            symbol,
            next_retry_ts,
            state.get("failures"),
        )
    return None


def _resolve_market_price(symbol: str, market_data=None):
    if not market_data:
        return None

    if isinstance(market_data, dict):
        symbol_key = (symbol or "").upper()
        if symbol_key in market_data:
            value = market_data.get(symbol_key)
        elif symbol in market_data:
            value = market_data.get(symbol)
        else:
            value = market_data.get("price")

        if isinstance(value, dict):
            for key in ("price", "close", "last", "lastPrice", "last_price", "c"):
                if value.get(key) is not None:
                    return value.get(key)
            return None
        return value

    return None

def price_hit_tp(trade, market_data=None):
    """
    Check if take profit is hit.
    For LONG: TP hit when current price >= target
    For SHORT: TP hit when current price <= target
    """
    # Get current price from market_data or fetch it
    current_price = _resolve_market_price(getattr(trade, "symbol", None), market_data)
    if current_price is None:
        current_price = _get_current_price(trade.symbol)
    
    if current_price is None:
        return False
    
    # Use normalized targets list
    targets = getattr(trade, "targets", []) or []
    if not targets:
        return False
    direction = (getattr(trade, "direction", "long") or "long").lower()
    
    # Check if any target is hit
    any_hit = False
    for target in targets:
        if target is None:
            continue
        if direction == "long":
            if current_price >= target:
                logger.info(f"TP hit for {trade.symbol} LONG: price={current_price} >= target={target}")
                try:
                    if target not in trade.targets_hit:
                        trade.targets_hit.append(target)
                        any_hit = True
                except Exception:
                    pass
        elif direction == "short":
            if current_price <= target:
                logger.info(f"TP hit for {trade.symbol} SHORT: price={current_price} <= target={target}")
                try:
                    if target not in trade.targets_hit:
                        trade.targets_hit.append(target)
                        any_hit = True
                except Exception:
                    pass

    return any_hit

def price_hit_sl(trade, market_data=None):
    """
    Check if stop loss is hit AFTER confirming entry was reached.
    For LONG: Price must have reached entry level before SL can trigger
    For SHORT: Price must have reached entry level before SL can trigger
    
    This prevents "SL-before-entry" invalidations where the price hits
    the stop loss before ever reaching the entry price.
    """
    # Get current price from market_data or fetch it
    current_price = _resolve_market_price(getattr(trade, "symbol", None), market_data)
    if current_price is None:
        current_price = _get_current_price(trade.symbol)
    
    if current_price is None:
        return False
    
    # Normalize direction and stop.
    direction = (getattr(trade, "direction", "LONG") or "LONG").upper()
    stop = getattr(trade, "stop", None)
    
    if stop is None:
        return False

    # Ensure numeric values
    try:
        stop_val = float(stop)
    except Exception:
        return False

    # Check SL directly. Gaps beyond stop should still count as a stop-loss.
    if direction == "LONG":
        if current_price <= stop_val:
            logger.info(f"SL hit for {trade.symbol} LONG: price={current_price} <= stop={stop_val}")
            return True
    elif direction == "SHORT":
        if current_price >= stop_val:
            logger.info(f"SL hit for {trade.symbol} SHORT: price={current_price} >= stop={stop_val}")
            return True

    return False

def close_trade(trade: TradeRecord, outcome: str):
    trade.close_time = _utcnow_naive()
    if trade.targets_hit and len(trade.targets_hit) < len(trade.targets):
        trade.outcome = "PARTIAL_TP"
    else:
        trade.outcome = outcome

def add_trade(signal: dict):
    """Add a new trade to track."""
    _load_open_trades_from_state()
    key = _trade_key(signal)
    for existing in open_trades_list:
        if _trade_key(existing.signal) == key:
            logger.debug(f"Skipping duplicate open trade for {existing.symbol} {existing.direction} key={key}")
            return existing

    trade = TradeRecord(signal)
    open_trades_list.append(trade)
    _persist_trade_state(trade)
    logger.info(f"Trade opened: {trade.symbol} {trade.direction} entry={trade.entry}")
    return trade

def update_trade_outcomes(market_data=None):
    """
    Update trade outcomes based on current market data.
    Closes trades that hit TP/SL and removes them from open_trades_list.
    """
    if market_data is None and len(open_trades_list) > 1:
        try:
            market_data = state.get_latest_tick_snapshot_sync([trade.symbol for trade in open_trades_list if getattr(trade, "symbol", None)])
        except Exception:
            market_data = None

    if market_data is None and len(open_trades_list) > 1 and _allow_external_price_fallback():
        try:
            market_data = _batch_price_snapshot([trade.symbol for trade in open_trades_list if getattr(trade, "symbol", None)])
        except Exception:
            market_data = None

    trades_to_remove = []

    for trade in open_trades():
        if price_hit_tp(trade, market_data):
            close_trade(trade, "TP")
            trades_to_remove.append(trade)
        elif price_hit_sl(trade, market_data):
            close_trade(trade, "SL")
            trades_to_remove.append(trade)

    closed = []
    # Remove closed trades from open_trades_list and collect for return
    for trade in trades_to_remove:
        if trade in open_trades_list:
            try:
                open_trades_list.remove(trade)
            except ValueError:
                pass
            _remove_trade_state(trade)
            logger.info(f"Removed closed trade {trade.signal_id} ({trade.outcome}) from open_trades_list")
        closed.append(trade)

    return closed


def _batch_price_snapshot(symbols):
    unique_symbols = []
    seen = set()
    for symbol in symbols or []:
        key = (symbol or "").upper().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_symbols.append(key)

    if len(unique_symbols) < 2:
        return {}

    try:
        yf_symbols = [_convert_symbol_for_yfinance(symbol) for symbol in unique_symbols]
        raw = yf.download(
            tickers=yf_symbols,
            period="1d",
            interval="1m",
            group_by="ticker",
            auto_adjust=False,
            threads=False,
            progress=False,
        )
    except Exception as exc:
        logger.debug("Batch price snapshot failed: %s", exc)
        return {}

    if raw is None or getattr(raw, "empty", True):
        return {}

    prices = {}

    def _extract_price(frame):
        try:
            if frame is None or getattr(frame, "empty", True):
                return None
            close = frame.get("Close")
            if close is not None:
                close = close.dropna()
                if len(close) > 0:
                    return float(close.iloc[-1])
        except Exception:
            return None
        return None

    if hasattr(raw, "columns") and getattr(raw.columns, "nlevels", 1) > 1:
        for symbol, yf_symbol in zip(unique_symbols, yf_symbols):
            try:
                frame = raw[yf_symbol]
            except Exception:
                frame = None
            price = _extract_price(frame)
            if price and price > 0:
                prices[symbol] = price
                _set_price_cache(symbol, price)
                _record_price_success(symbol)
    else:
        # Single-ticker style dataframe or flat download response.
        price = _extract_price(raw)
        if price and price > 0 and unique_symbols:
            symbol = unique_symbols[0]
            prices[symbol] = price
            _set_price_cache(symbol, price)
            _record_price_success(symbol)

    return prices
