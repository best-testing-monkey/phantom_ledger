from __future__ import annotations

import sqlite3
import threading

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.db.repositories.equity_repo import EquityRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.position_manager import PositionManager
from phantom.errors import ValidationError
from phantom.models.equity_point import EquityPoint
from phantom.models.position import Position
from phantom.utils.datetime import now_utc, to_iso


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
        self,
        position_id: str,
        close_reason: str = "manual",
        exit_price: float | None = None,
        quantity: float | None = None,
        exit_datetime=None,
    ) -> Position:
        with self._lock:
            position = self._position_repo.get(position_id)
            if position.status != "open":
                raise ValidationError(f"Position {position_id} is already {position.status}")

            if exit_price is None:
                raise ValidationError("exit_price is required")

            # Validate and default quantity
            if quantity is None:
                quantity = position.quantity
            if quantity <= 0:
                raise ValidationError("Quantity must be greater than zero")
            if quantity > position.quantity:
                raise ValidationError("Quantity exceeds open position size")

            account = self._account_repo.get(position.account_id)
            profile = self._broker_repo.get(account.broker_profile_id)
            cost_engine = CostEngine(profile)

            # Calculate exit costs for the closing quantity
            costs = cost_engine.exit_costs(
                price=exit_price,
                quantity=quantity,
                ticker=position.ticker,
                instrument_type=position.instrument_type,
            )

            # Check if this is a full close
            if quantity == position.quantity:
                # Full close: use existing manager close logic
                manager = PositionManager(self._position_repo, self._account_repo, cost_engine)
                closed = manager.close(
                    position, exit_price, close_reason, exit_datetime or now_utc()
                )
                account_before = self._account_repo.get(position.account_id)
                account_updated = account_before.model_copy(
                    update={
                        "cash": account_before.cash
                        + manager.close_cash_return(position, closed, costs)
                    }
                )
                self._position_repo.update(closed)
                self._account_repo.update(account_updated)
                # Record equity snapshot so the chart reflects the closed cash value
                EquityRepo(self._conn).create(
                    EquityPoint(
                        account_id=position.account_id,
                        timestamp=to_iso(closed.exit_datetime),
                        equity=account_updated.cash,
                        cash=account_updated.cash,
                        unrealized_pnl=0.0,
                    )
                )
                return closed
            else:
                # Partial close: decrement position quantity, accumulate realized P&L
                fraction = quantity / position.quantity
                proportional_entry_costs = (
                    position.commission_entry
                    + position.spread_cost
                    + position.slippage_cost
                    + position.fx_conversion_cost
                ) * fraction

                if position.direction == "long":
                    gross_pnl = (exit_price - position.entry_price) * quantity
                else:
                    gross_pnl = (position.entry_price - exit_price) * quantity

                realized_pnl_increment = gross_pnl - proportional_entry_costs - costs.total
                new_realized_pnl = (position.realized_pnl or 0) + realized_pnl_increment

                # Update position: decrement quantity, accumulate realized P&L
                updated_position = position.model_copy(
                    update={
                        "quantity": position.quantity - quantity,
                        "realized_pnl": new_realized_pnl,
                        "commission_exit": position.commission_exit + costs.commission,
                    }
                )

                # Credit cash to account
                account_before = self._account_repo.get(position.account_id)
                if position.instrument_type == "cfd":
                    released_margin = position.margin_required * fraction
                    cash_delta = released_margin + gross_pnl - costs.total
                else:
                    cash_delta = exit_price * quantity - costs.total
                account_updated = account_before.model_copy(
                    update={"cash": account_before.cash + cash_delta}
                )

                self._position_repo.update(updated_position)
                self._account_repo.update(account_updated)
                return updated_position

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
