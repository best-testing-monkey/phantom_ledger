from __future__ import annotations

from datetime import datetime
import sqlite3
import threading

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.db.repositories.order_repo import OrderRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.order_manager import OrderManager
from phantom.errors import ValidationError
from phantom.models.order import Order
from phantom.models.position import Position
from phantom.utils.datetime import now_utc


class OrderAPI:
    def __init__(
        self, conn: sqlite3.Connection, broker_repo: BrokerRepo, lock: threading.RLock | None = None
    ):
        self._conn = conn
        self._order_repo = OrderRepo(conn)
        self._account_repo = AccountRepo(conn)
        self._broker_repo = broker_repo
        self._lock = lock or threading.RLock()

    def _get_manager(self, account_id: str) -> OrderManager:
        account = self._account_repo.get(account_id)
        profile = self._broker_repo.get(account.broker_profile_id)
        cost_engine = CostEngine(profile)
        return OrderManager(self._order_repo, self._account_repo, cost_engine)

    def place(self, account_id: str, order: Order) -> Order:
        with self._lock:
            # Validate CFD/short instrument support
            account = self._account_repo.get(account_id)
            profile = self._broker_repo.get(account.broker_profile_id)

            # Check if trying to trade CFD on a broker that doesn't support it
            if order.instrument_type == "cfd" and "cfd" not in profile.supported_instruments:
                msg = f"Broker {profile.name} does not support instrument type: cfd"
                raise ValidationError(msg)

            # Check if trying to short on a broker that only supports stocks
            if order.direction == "short" and "cfd" not in profile.supported_instruments:
                msg = f"Broker {profile.name} does not support short positions"
                raise ValidationError(msg)

            manager = self._get_manager(account_id)
            return manager.place(account_id, order)

    def list(self, account_name: str | None = None, status: str | None = None) -> list[Order]:
        if account_name is None:
            return []
        account = self._account_repo.get_by_name(account_name)
        return self._order_repo.list_by_account(account.id, status=status)

    def cancel(self, order_id: str) -> Order:
        order = self._order_repo.get(order_id)
        if order.status not in ("pending",):
            raise ValidationError(f"Cannot cancel order with status '{order.status}'")
        return self._order_repo.update_status(order_id, "cancelled")

    def fill_manual(
        self,
        order_id: str,
        fill_price: float,
        fill_datetime: datetime | None = None,
    ) -> tuple[Order, Position]:
        """Manually fill a pending order at a specified price, creating a position."""
        with self._lock:
            order = self._order_repo.get(order_id)
            if order.status != "pending":
                raise ValidationError(f"Cannot fill order with status '{order.status}'")
            if fill_price <= 0:
                raise ValidationError("Fill price must be greater than zero")
            fill_dt = fill_datetime or now_utc()
            # Stamp the order with fill details so handle_fill can read them
            order = order.model_copy(update={"fill_price": fill_price, "filled_at": fill_dt})
            manager = self._get_manager(order.account_id)
            position_repo = PositionRepo(self._conn)
            return manager.handle_fill(order, position_repo)

    def modify(
        self,
        order_id: str,
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Order:
        with self._lock:
            order = self._order_repo.get(order_id)
            if order.status != "pending":
                raise ValidationError(f"Cannot modify order with status '{order.status}'")
            updates = {}
            if limit_price is not None:
                updates["limit_price"] = limit_price
            if stop_loss is not None:
                updates["stop_loss"] = stop_loss
            if take_profit is not None:
                updates["take_profit"] = take_profit
            if not updates:
                raise ValidationError("Provide at least one field to modify")
            return self._order_repo.update_prices(order_id, updates)
