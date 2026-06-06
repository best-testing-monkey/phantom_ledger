from datetime import datetime
import logging

import pandas as pd

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.order_repo import OrderRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.errors import InsufficientFundsError
from phantom.models.order import Order
from phantom.models.position import Position
from phantom.utils.datetime import now_utc

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(
        self,
        order_repo: OrderRepo,
        account_repo: AccountRepo,
        cost_engine: CostEngine,
    ):
        self._order_repo = order_repo
        self._account_repo = account_repo
        self._cost_engine = cost_engine

    def place(self, account_id: str, order: Order) -> Order:
        account = self._account_repo.get(account_id)
        if not order.created_at:
            order = order.model_copy(update={"created_at": now_utc()})

        estimated_price = order.limit_price or order.stop_price or 0.0
        if order.order_type == "market":
            estimated_cost = 0.0
        else:
            estimated_cost = estimated_price * order.quantity
            if account.cash < estimated_cost:
                raise InsufficientFundsError(
                    account_id=account_id,
                    required=estimated_cost,
                    available=account.cash,
                )
        return self._order_repo.create(
            order.model_copy(update={"account_id": account_id, "status": "pending"})
        )

    def evaluate(self, bar: pd.Series, pending_orders: list[Order]) -> list[Order]:
        filled = []
        for order in pending_orders:
            if order.order_type == "market":
                filled.append(
                    order.model_copy(
                        update={
                            "status": "filled",
                            "fill_price": float(bar["Open"]),
                            "filled_at": bar.name.to_pydatetime()
                            if hasattr(bar.name, "to_pydatetime")
                            else bar.name,
                        }
                    )
                )
            elif order.order_type == "limit":
                if order.direction == "long" and float(bar["Low"]) <= order.limit_price:
                    filled.append(
                        order.model_copy(
                            update={
                                "status": "filled",
                                "fill_price": order.limit_price,
                                "filled_at": bar.name.to_pydatetime()
                                if hasattr(bar.name, "to_pydatetime")
                                else bar.name,
                            }
                        )
                    )
                elif order.direction == "short" and float(bar["High"]) >= order.limit_price:
                    filled.append(
                        order.model_copy(
                            update={
                                "status": "filled",
                                "fill_price": order.limit_price,
                                "filled_at": bar.name.to_pydatetime()
                                if hasattr(bar.name, "to_pydatetime")
                                else bar.name,
                            }
                        )
                    )
        return filled

    def handle_fill(self, order: Order, position_repo: PositionRepo) -> tuple[Order, Position]:
        account = self._account_repo.get(order.account_id)
        costs = self._cost_engine.entry_costs(
            price=order.fill_price,
            quantity=order.quantity,
            ticker=order.ticker,
            instrument_type=order.instrument_type,
            fx_required=(account.base_currency != "USD"),
        )
        total_deduction = order.fill_price * order.quantity + costs.total
        if account.cash < total_deduction:
            raise InsufficientFundsError(
                account_id=order.account_id,
                required=total_deduction,
                available=account.cash,
            )
        position = Position(
            account_id=order.account_id,
            ticker=order.ticker,
            instrument_type=order.instrument_type,
            direction=order.direction,
            entry_order_id=order.id,
            entry_price=order.fill_price,
            entry_datetime=order.filled_at,
            quantity=order.quantity,
            notional=order.fill_price * order.quantity,
            take_profit=order.take_profit,
            stop_loss=order.stop_loss,
            max_close_datetime=order.max_close_datetime,
            commission_entry=costs.commission,
            spread_cost=costs.spread,
            slippage_cost=costs.slippage,
            fx_conversion_cost=costs.fx,
        )
        account = account.model_copy(update={"cash": account.cash - total_deduction})
        position_repo.create(position)
        self._order_repo.update_status(order.id, "filled", position_id=position.id)
        self._account_repo.update(account)
        logger.info("Order %s filled at %.2f", order.id, order.fill_price)
        return self._order_repo.get(order.id), position

    def expire_orders(
        self, pending_orders: list[Order], now: datetime
    ) -> tuple[list[Order], list[Order]]:
        active, expired = [], []
        for order in pending_orders:
            if order.good_til is not None and order.good_til < now:
                logger.info("Order %s expired (good_til=%s)", order.id, order.good_til)
                expired.append(order.model_copy(update={"status": "expired"}))
            else:
                active.append(order)
        return active, expired
