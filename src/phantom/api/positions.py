from __future__ import annotations

import sqlite3
import threading

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.position_manager import PositionManager
from phantom.errors import ValidationError
from phantom.models.position import Position
from phantom.utils.datetime import now_utc


class PositionAPI:
    def __init__(
        self, conn: sqlite3.Connection, broker_repo: BrokerRepo, lock: threading.RLock | None = None
    ):
        self._conn = conn
        self._position_repo = PositionRepo(conn)
        self._account_repo = AccountRepo(conn)
        self._broker_repo = broker_repo
        self._lock = lock or threading.RLock()

    def list(
        self,
        account_name: str | None = None,
        status: str | None = None,
        replay_completed_at=...,
        pattern_tag: str | None = None,
        algorithm_version: str | None = None,
    ) -> list[Position]:
        if account_name:
            account = self._account_repo.get_by_name(account_name)
            return self._position_repo.list_by_account(
                account.id,
                status=status,
                replay_completed_at=replay_completed_at,
                pattern_tag=pattern_tag,
                algorithm_version=algorithm_version,
            )
        return self._position_repo.list_open_all()

    def get(self, position_id: str) -> Position:
        return self._position_repo.get(position_id)

    def close(
        self, position_id: str, close_reason: str = "manual", exit_price: float | None = None
    ) -> Position:
        with self._lock:
            position = self._position_repo.get(position_id)
            if position.status != "open":
                raise ValidationError(f"Position {position_id} is already {position.status}")

            account = self._account_repo.get(position.account_id)
            profile = self._broker_repo.get(account.broker_profile_id)
            cost_engine = CostEngine(profile)
            manager = PositionManager(self._position_repo, self._account_repo, cost_engine)

            if exit_price is None:
                raise ValidationError("exit_price is required")

            closed = manager.close(position, exit_price, close_reason, now_utc())

            costs = cost_engine.exit_costs(
                price=exit_price,
                quantity=position.quantity,
                ticker=position.ticker,
                instrument_type=position.instrument_type,
            )
            account_before = self._account_repo.get(position.account_id)
            account_updated = account_before.model_copy(
                update={"cash": account_before.cash + exit_price * position.quantity - costs.total}
            )

            self._position_repo.update(closed)
            self._account_repo.update(account_updated)
            return closed

    def modify(
        self, position_id: str, take_profit: float | None = None, stop_loss: float | None = None
    ) -> Position:
        with self._lock:
            position = self._position_repo.get(position_id)
            if position.status != "open":
                raise ValidationError(f"Cannot modify a {position.status} position")
            updates = {}
            if take_profit is not None:
                updates["take_profit"] = take_profit
            if stop_loss is not None:
                updates["stop_loss"] = stop_loss
            if not updates:
                raise ValidationError("Provide at least take_profit or stop_loss")
            updated = position.model_copy(update=updates)
            return self._position_repo.update(updated)

    def reset_replay(self, position_id: str) -> None:
        self._position_repo.reset_replay(position_id)
