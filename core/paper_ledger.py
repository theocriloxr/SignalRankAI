import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import uuid4

from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)

# Default paper trading balance
DEFAULT_PAPER_BALANCE = 10000.0


class PaperPosition:
    """
    Lightweight value-object wrapping a position dict.

    Used by tests and in-memory position tracking where a full SQLAlchemy
    model is not available.  The ``check_tp_sl_hit`` method in PaperLedger
    expects attribute access to ``asset``, ``direction``, ``stop_loss``,
    ``target_price`` and ``position_id``.

    ``take_profit`` is parsed into ``target_price`` at construction time so
    callers can pass either a list of dicts/floats or a plain float/str.
    """

    def __init__(self, data: dict) -> None:
        self._data = data

    def _extract_tp(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        # JSON string
        if isinstance(value, str):
            import json as _json
            try:
                value = _json.loads(value)
            except Exception:
                try:
                    return float(value)
                except Exception:
                    return None
        # List of dicts or floats
        if isinstance(value, (list, tuple)) and value:
            first = value[0]
            if isinstance(first, dict):
                for key in ("price", "tp", "target", "target_price"):
                    if key in first:
                        try:
                            return float(first[key])
                        except Exception:
                            pass
                return None
            try:
                return float(first)
            except Exception:
                return None
        # Plain float/int
        try:
            return float(value)
        except Exception:
            return None

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name == "target_price":
            return self._extract_tp(self._data.get("take_profit"))
        if name == "entry_price":
            return self._data.get("entry_price") or self._data.get("fill_entry") or self._data.get("entry")
        if name == "fill_entry":
            return self._data.get("fill_entry") or self._data.get("entry_price") or self._data.get("entry")
        return self._data.get(name)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __repr__(self) -> str:
        return f"PaperPosition({self._data!r})"


class PaperLedger:
    """
    Paper trading ledger for managing virtual accounts and positions.
    Uses immutable, double-entry transactional accounting.
    """

    def __init__(self):
        pass

    async def get_balance(self, user_id: int) -> float:
        """Get a user's virtual account balance (creates account if none)."""
        from db.session import get_session
        from db.models import PaperAccount
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(select(PaperAccount).where(PaperAccount.user_id == user_id))
            account = result.scalar_one_or_none()
            if not account:
                account = PaperAccount(
                    user_id=user_id, starting_balance=DEFAULT_PAPER_BALANCE, cash_balance=DEFAULT_PAPER_BALANCE
                )
                session.add(account)
                await session.commit()
                return DEFAULT_PAPER_BALANCE
            return float(account.cash_balance)

    async def set_balance(self, user_id: int, balance: float) -> None:
        """Set a user's virtual account balance."""
        from db.session import get_session
        from db.models import PaperAccount
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(select(PaperAccount).where(PaperAccount.user_id == user_id))
            account = result.scalar_one_or_none()
            if account:
                account.cash_balance = balance
                await session.commit()

    async def _get_account(self, session, user_id: int):
        from db.models import PaperAccount
        from sqlalchemy import select

        result = await session.execute(select(PaperAccount).where(PaperAccount.user_id == user_id))
        account = result.scalar_one_or_none()
        if not account:
            account = PaperAccount(
                user_id=user_id, starting_balance=DEFAULT_PAPER_BALANCE, cash_balance=DEFAULT_PAPER_BALANCE
            )
            session.add(account)
            await session.flush()
        return account

    async def open_position(
        self, user_id: int, signal: Dict[str, Any], size: Optional[float] = None, risk_pct: float = 1.0
    ) -> Optional[Any]:  # Returns the PaperPosition model instance
        from db.session import get_session
        from db.models import PaperPosition, PaperLedgerEntry

        async with get_session() as session:
            account = await self._get_account(session, user_id)
            balance = account.cash_balance

            if size is None:
                entry = float(signal.get("entry", 0))
                stop_loss = float(signal.get("stop_loss") or signal.get("stop", 0))
                if entry > 0 and stop_loss > 0:
                    risk_amount = balance * (risk_pct / 100.0)
                    risk_per_unit = abs(entry - stop_loss)
                    if risk_per_unit > 0:
                        size = risk_amount / risk_per_unit

            if size is None or size <= 0:
                size = balance * 0.01

            entry = float(signal.get("entry", 0))
            entry_value = size * entry

            if entry_value > balance:
                size = balance / entry
                entry_value = size * entry

            position_id = f"paper_{user_id}_{signal.get('asset', 'unknown')}_{int(now_utc_naive().timestamp())}"

            pos = PaperPosition(
                position_id=position_id,
                account_id=account.id,
                user_id=user_id,
                signal_id=signal.get("signal_id", str(uuid4())),
                asset=signal.get("asset", "unknown"),
                direction=signal.get("direction", "long"),
                status="open",
                signal_entry=entry,
                fill_entry=entry,
                current_price=entry,
                stop_loss=float(signal.get("stop_loss") or 0.0),
                quantity=size,
                notional=entry_value,
                reserved_cash=entry_value,
                opened_at=now_utc_naive(),
            )
            session.add(pos)

            account.cash_balance -= entry_value

            entry_log = PaperLedgerEntry(
                account_id=account.id,
                user_id=user_id,
                position_id=position_id,
                entry_type="TRADE_OPEN",
                amount=-entry_value,
                balance_after=account.cash_balance,
                description=f"Opened {pos.direction} {size} {pos.asset} at {entry}",
            )
            session.add(entry_log)
            await session.commit()
            return pos

    async def close_position(
        self, user_id: int, position_id: str, exit_reason: str, exit_price: float, exit_time: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        if exit_time is None:
            exit_time = now_utc_naive()

        from db.session import get_session
        from db.models import PaperPosition, PaperLedgerEntry
        from sqlalchemy import select

        async with get_session() as session:
            account = await self._get_account(session, user_id)
            result = await session.execute(
                select(PaperPosition).where(PaperPosition.position_id == position_id, PaperPosition.user_id == user_id)
            )
            pos = result.scalar_one_or_none()

            if not pos or pos.status != "open":
                return None

            direction = pos.direction.lower()
            if direction == "long":
                pnl = (exit_price - pos.fill_entry) * pos.quantity
            else:
                pnl = (pos.fill_entry - exit_price) * pos.quantity

            risk = abs(pos.fill_entry - pos.stop_loss) if pos.stop_loss > 0 else 0
            r_multiple = pnl / (risk * pos.quantity) if risk > 0 and pos.quantity > 0 else 0

            pos.status = "closed"
            pos.closed_at = exit_time
            pos.exit_reason = exit_reason
            pos.realized_pnl = pnl
            pos.r_multiple = r_multiple
            pos.current_price = exit_price

            # Return reserved cash + pnl
            amount_to_return = pos.reserved_cash + pnl
            account.cash_balance += amount_to_return
            account.realized_pnl += pnl

            entry_type = "TRADE_WIN" if pnl > 0 else "TRADE_LOSS"
            entry_log = PaperLedgerEntry(
                account_id=account.id,
                user_id=user_id,
                position_id=position_id,
                entry_type=entry_type,
                amount=amount_to_return,
                balance_after=account.cash_balance,
                description=f"Closed {pos.asset} {exit_reason}: {pnl:+.2f} ({r_multiple:+.2f}R)",
            )
            session.add(entry_log)
            await session.commit()

            return {
                "position_id": position_id,
                "pnl": pnl,
                "r_multiple": r_multiple,
                "exit_reason": exit_reason,
                "new_balance": account.cash_balance,
            }

    async def _get_position(self, position_id: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        from db.session import get_session
        from db.models import PaperPosition
        from sqlalchemy import select

        async with get_session() as session:
            stmt = select(PaperPosition).where(PaperPosition.position_id == position_id)
            if user_id:
                stmt = stmt.where(PaperPosition.user_id == user_id)
            result = await session.execute(stmt)
            pos = result.scalar_one_or_none()
            if pos:
                return {
                    "position_id": pos.position_id,
                    "user_id": pos.user_id,
                    "signal_id": pos.signal_id,
                    "asset": pos.asset,
                    "direction": pos.direction,
                    "status": pos.status,
                    "entry_price": pos.fill_entry,
                    "stop_loss": pos.stop_loss,
                    "size": pos.quantity,
                }
        return None

    async def get_open_positions(self, user_id: int) -> List[Any]:
        from db.session import get_session
        from db.models import PaperPosition
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(
                select(PaperPosition).where(PaperPosition.user_id == user_id, PaperPosition.status == "open")
            )
            return list(result.scalars().all())

    async def _add_ledger_entry(self, user_id: int, amount: float, entry_type: str, description: str) -> None:
        from db.session import get_session
        from db.models import PaperLedgerEntry

        async with get_session() as session:
            account = await self._get_account(session, user_id)
            account.cash_balance += amount
            entry_log = PaperLedgerEntry(
                account_id=account.id,
                user_id=user_id,
                entry_type=entry_type,
                amount=amount,
                balance_after=account.cash_balance,
                description=description,
            )
            session.add(entry_log)
            await session.commit()

    async def check_tp_sl_hit(self, user_id: int, asset: str, current_price: float) -> Optional[str]:
        positions = await self.get_open_positions(user_id)
        hit_reason = None
        for pos in positions:
            if pos.asset != asset:
                continue

            direction = pos.direction.lower()
            try:
                sl = float(pos.stop_loss or 0)
            except Exception:
                sl = 0.0
            try:
                tp = float(pos.target_price or 0)
            except Exception:
                tp = 0.0

            if direction == "long":
                if sl > 0 and current_price <= sl:
                    try:
                        await self.close_position(user_id, pos.position_id, "SL", sl)
                    except Exception:
                        pass
                    hit_reason = "SL"
                elif tp > 0 and current_price >= tp:
                    try:
                        await self.close_position(user_id, pos.position_id, "TP", tp)
                    except Exception:
                        pass
                    hit_reason = "TP"
            else:
                if sl > 0 and current_price >= sl:
                    try:
                        await self.close_position(user_id, pos.position_id, "SL", sl)
                    except Exception:
                        pass
                    hit_reason = "SL"
                elif tp > 0 and current_price <= tp:
                    try:
                        await self.close_position(user_id, pos.position_id, "TP", tp)
                    except Exception:
                        pass
                    hit_reason = "TP"
        return hit_reason


def get_paper_ledger() -> PaperLedger:
    return PaperLedger()


async def sync_execution(
    signal_id: str,
    user_id: int,
    order_id: str,
    asset: str,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: Any,
    volume: float,
    status: str = "executed",
) -> Optional[Any]:
    signal = {
        "signal_id": signal_id,
        "broker_order_id": order_id,
        "asset": asset,
        "direction": direction,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "execution_status": status,
    }
    ledger = get_paper_ledger()
    position = await ledger.open_position(
        user_id=int(user_id),
        signal=signal,
        size=float(volume or 0.0) if volume is not None else None,
        risk_pct=1.0,
    )
    if position:
        await ledger._add_ledger_entry(
            int(user_id),
            0.0,
            "LIVE_SYNC",
            f"Synced live order {order_id or 'unknown'} for {asset} {direction}",
        )
    return position
