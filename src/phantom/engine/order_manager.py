from datetime import datetime
import logging

import pandas as pd

from phantom.costs.engine import CostEngine
from phantom.costs.margin import compute_margin_required
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.db.repositories.order_repo import OrderRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.errors import InsufficientFundsError, MarginError, ValidationError
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
        broker_repo: BrokerRepo | None = None,
    ):
        self._order_repo = order_repo
        self._account_repo = account_repo
        self._cost_engine = cost_engine
        self._broker_repo = broker_repo

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

        # Margin validation for CFD orders
        if order.instrument_type == "cfd" and self._broker_repo is not None:
            broker_profile = self._broker_repo.get(account.broker_profile_id)
            required_margin = (
                estimated_price
                * order.quantity
                * broker_profile.margin.margin_pct_for(order.ticker)
            )
            if account.cash < required_margin:
                raise MarginError(account_id=account_id, margin_level=0.0)

        return self._order_repo.create(
            order.model_copy(update={"account_id": account_id, "status": "pending"})
        )

    def place_or_reject(self, account_id: str, order: Order) -> Order:
        """Place order, or return with status='rejected' if validation fails."""
        try:
            return self.place(account_id, order)
        except InsufficientFundsError:
            rejected_order = order.model_copy(
                update={
                    "account_id": account_id,
                    "status": "rejected",
                    "rejection_reason": "insufficient_funds",
                    "created_at": order.created_at or now_utc(),
                }
            )
            return self._order_repo.create(rejected_order)
        except MarginError:
            rejected_order = order.model_copy(
                update={
                    "account_id": account_id,
                    "status": "rejected",
                    "rejection_reason": "insufficient_margin",
                    "created_at": order.created_at or now_utc(),
                }
            )
            return self._order_repo.create(rejected_order)
        except ValidationError as e:
            reason = "unsupported_instrument"
            if "trading hours" in str(e):
                reason = "outside_trading_hours"
            rejected_order = order.model_copy(
                update={
                    "account_id": account_id,
                    "status": "rejected",
                    "rejection_reason": reason,
                    "created_at": order.created_at or now_utc(),
                }
            )
            return self._order_repo.create(rejected_order)

    def evaluate(self, bar: pd.Series, pending_orders: list[Order]) -> list[Order]:
        filled = []
        for order in pending_orders:
            bar_timestamp = (
                bar.name.to_pydatetime() if hasattr(bar.name, "to_pydatetime") else bar.name
            )

            if order.order_type == "market":
                filled.append(
                    order.model_copy(
                        update={
                            "status": "filled",
                            "fill_price": float(bar["Open"]),
                            "filled_at": bar_timestamp,
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
                                "filled_at": bar_timestamp,
                            }
                        )
                    )
                elif order.direction == "short" and float(bar["High"]) >= order.limit_price:
                    filled.append(
                        order.model_copy(
                            update={
                                "status": "filled",
                                "fill_price": order.limit_price,
                                "filled_at": bar_timestamp,
                            }
                        )
                    )

            elif order.order_type == "stop":
                # Stop order: triggers when stop price is hit, fills at open or worse
                if order.direction == "long" and float(bar["High"]) >= order.stop_price:
                    # Buy stop: fill at max of stop price and open
                    fill_price = max(order.stop_price, float(bar["Open"]))
                    filled.append(
                        order.model_copy(
                            update={
                                "status": "filled",
                                "fill_price": fill_price,
                                "filled_at": bar_timestamp,
                            }
                        )
                    )
                elif order.direction == "short" and float(bar["Low"]) <= order.stop_price:
                    # Sell stop: fill at min of stop price and open
                    fill_price = min(order.stop_price, float(bar["Open"]))
                    filled.append(
                        order.model_copy(
                            update={
                                "status": "filled",
                                "fill_price": fill_price,
                                "filled_at": bar_timestamp,
                            }
                        )
                    )

            elif order.order_type == "stop_limit":
                # Stop-limit: triggers when stop hit, then acts as limit
                if order.status == "pending":
                    # Check if stop is triggered
                    stop_triggered = False
                    if order.direction == "long" and float(bar["High"]) >= order.stop_price:
                        stop_triggered = True
                    elif order.direction == "short" and float(bar["Low"]) <= order.stop_price:
                        stop_triggered = True

                    if stop_triggered:
                        # Transition to triggered status
                        triggered_order = order.model_copy(
                            update={
                                "status": "triggered",
                                "triggered_at": bar_timestamp,
                            }
                        )
                        # Attempt to fill at limit price in same bar
                        if order.direction == "long" and float(bar["Low"]) <= order.limit_price:
                            filled.append(
                                triggered_order.model_copy(
                                    update={
                                        "status": "filled",
                                        "fill_price": order.limit_price,
                                        "filled_at": bar_timestamp,
                                    }
                                )
                            )
                        elif order.direction == "short" and float(bar["High"]) >= order.limit_price:
                            filled.append(
                                triggered_order.model_copy(
                                    update={
                                        "status": "filled",
                                        "fill_price": order.limit_price,
                                        "filled_at": bar_timestamp,
                                    }
                                )
                            )

                elif order.status == "triggered":
                    # Already triggered, check limit fill condition
                    if order.direction == "long" and float(bar["Low"]) <= order.limit_price:
                        filled.append(
                            order.model_copy(
                                update={
                                    "status": "filled",
                                    "fill_price": order.limit_price,
                                    "filled_at": bar_timestamp,
                                }
                            )
                        )
                    elif order.direction == "short" and float(bar["High"]) >= order.limit_price:
                        filled.append(
                            order.model_copy(
                                update={
                                    "status": "filled",
                                    "fill_price": order.limit_price,
                                    "filled_at": bar_timestamp,
                                }
                            )
                        )

            elif order.order_type == "trailing_stop":
                # Trailing stop: updates peak on each bar, triggers when distance exceeded
                # Initialize peak if first time (order.trailing_peak is None)
                if order.trailing_peak is None:
                    # First bar - just set peak, don't trigger
                    if order.direction == "long":
                        new_peak = float(bar["High"])
                    else:
                        new_peak = float(bar["Low"])
                    # Don't add to filled - just record the peak for next bar
                else:
                    trailing_peak = order.trailing_peak

                    if order.direction == "long":
                        # Long trailing stop: peak is max price seen
                        new_peak = max(trailing_peak, float(bar["High"]))
                        # Calculate trigger level
                        if order.trailing_amount is not None:
                            trigger_level = new_peak - order.trailing_amount
                        else:
                            trigger_level = new_peak * (1.0 - (order.trailing_pct or 0.0))

                        # Check if triggered
                        if float(bar["Low"]) <= trigger_level:
                            fill_price = max(trigger_level, float(bar["Open"]))
                            filled.append(
                                order.model_copy(
                                    update={
                                        "status": "filled",
                                        "fill_price": fill_price,
                                        "filled_at": bar_timestamp,
                                        "trailing_peak": new_peak,
                                    }
                                )
                            )

                    else:
                        # Short trailing stop: peak is min price seen
                        new_peak = min(trailing_peak, float(bar["Low"]))
                        # Calculate trigger level
                        if order.trailing_amount is not None:
                            trigger_level = new_peak + order.trailing_amount
                        else:
                            trigger_level = new_peak * (1.0 + (order.trailing_pct or 0.0))

                        # Check if triggered
                        if float(bar["High"]) >= trigger_level:
                            fill_price = min(trigger_level, float(bar["Open"]))
                            filled.append(
                                order.model_copy(
                                    update={
                                        "status": "filled",
                                        "fill_price": fill_price,
                                        "filled_at": bar_timestamp,
                                        "trailing_peak": new_peak,
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
        notional = order.fill_price * order.quantity
        if order.instrument_type == "cfd" and self._broker_repo is not None:
            broker_profile = self._broker_repo.get(account.broker_profile_id)
            margin_pct = broker_profile.margin.margin_pct_for(order.ticker)
            margin_required = compute_margin_required(order.quantity, order.fill_price, margin_pct)
            leverage = 1.0 / margin_pct if margin_pct > 0 else 1.0
            total_deduction = margin_required + costs.total
        else:
            margin_required = 0.0
            leverage = 1.0
            total_deduction = notional + costs.total
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
            notional=notional,
            take_profit=order.take_profit,
            stop_loss=order.stop_loss,
            max_close_datetime=order.max_close_datetime,
            commission_entry=costs.commission,
            spread_cost=costs.spread,
            slippage_cost=costs.slippage,
            fx_conversion_cost=costs.fx,
            margin_required=margin_required,
            leverage=leverage,
        )
        account = account.model_copy(update={"cash": account.cash - total_deduction})
        position_repo.create(position)
        self._order_repo.update_status(
            order.id,
            "filled",
            position_id=position.id,
            fill_price=order.fill_price,
            filled_at=order.filled_at,
        )
        self._account_repo.update(account)
        logger.info("Order %s filled at %.2f", order.id, order.fill_price)
        return self._order_repo.get(order.id), position

    def handle_fill_or_reject(
        self, order: Order, position_repo: PositionRepo
    ) -> tuple[Order, Position | None]:
        """Fill an order, or mark it rejected if it can't be funded.

        Unlike place_or_reject() (which creates a brand-new rejected order
        row because the order doesn't exist yet at that point), the order
        here already exists as a pending row — on failure this updates that
        same row to status="rejected" rather than inserting a duplicate.

        Returns (order, position) on success, or (rejected_order, None) if
        the fill couldn't be funded.
        """
        try:
            return self.handle_fill(order, position_repo)
        except InsufficientFundsError:
            rejected = self._order_repo.update_status(
                order.id, "rejected", rejection_reason="insufficient_funds"
            )
            return rejected, None

    def create_oco_pair(
        self, account_id: str, take_profit_order: Order, stop_loss_order: Order
    ) -> tuple[Order, Order]:
        """Create a one-cancels-other pair of orders.

        Args:
            account_id: Account ID for both orders
            take_profit_order: The take-profit leg (typically stop order)
            stop_loss_order: The stop-loss leg (typically limit order)

        Returns:
            Tuple of placed (tp_order, sl_order) with oco_sibling_id set
        """
        # Place both orders and link them
        tp_order = take_profit_order.model_copy(
            update={"account_id": account_id, "status": "pending"}
        )
        sl_order = stop_loss_order.model_copy(
            update={"account_id": account_id, "status": "pending"}
        )

        # Create TP order first
        tp_placed = self._order_repo.create(tp_order)

        # Create SL order with link to TP
        sl_with_link = sl_order.model_copy(update={"oco_sibling_id": tp_placed.id})
        sl_placed = self._order_repo.create(sl_with_link)

        # Update TP order with link to SL
        self._order_repo.update_status(tp_placed.id, "pending", oco_sibling_id=sl_placed.id)

        return self._order_repo.get(tp_placed.id), sl_placed

    def handle_oco_fill(self, filled_order: Order) -> Order:
        """Cancel the sibling order in an OCO pair when one fills."""
        if filled_order.oco_sibling_id:
            logger.info(
                "Order %s filled; cancelling OCO sibling %s",
                filled_order.id,
                filled_order.oco_sibling_id,
            )
            self._order_repo.update_status(filled_order.oco_sibling_id, "cancelled")
        return filled_order

    def update_trailing_peak(self, order_id: str, new_peak: float) -> Order:
        """Update trailing_peak for a trailing stop order."""
        return self._order_repo.update_status(order_id, "pending", trailing_peak=new_peak)

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
