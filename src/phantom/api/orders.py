from __future__ import annotations

import sqlite3
import threading

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.db.repositories.order_repo import OrderRepo
from phantom.engine.order_manager import OrderManager
from phantom.errors import ValidationError
from phantom.models.order import Order


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
