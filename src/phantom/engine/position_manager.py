from datetime import datetime
import logging

import pandas as pd

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.models.position import Position

logger = logging.getLogger(__name__)


def resolve_tp_sl_conflict(position: Position, bar: pd.Series, mode: str) -> str:
    """Determine which triggered first when both TP and SL are hit in same bar.

    Args:
        position: The position
        bar: Price bar with Open/High/Low/Close
        mode: "conservative" (SL), "optimistic" (TP), or "proximity"

    Returns:
        "tp" or "sl"
    """
    if mode == "conservative":
        return "sl"
    if mode == "optimistic":
        return "tp"
    if mode == "proximity":
        open_price = float(bar["Open"])
        tp_dist = abs(open_price - position.take_profit) if position.take_profit else float("inf")
        sl_dist = abs(open_price - position.stop_loss) if position.stop_loss else float("inf")
        return "tp" if tp_dist <= sl_dist else "sl"
    return "sl"


class PositionManager:
    def __init__(
        self, position_repo: PositionRepo, account_repo: AccountRepo, cost_engine: CostEngine
    ):
        self._position_repo = position_repo
        self._account_repo = account_repo
        self._cost_engine = cost_engine

    def update(self, position: Position, bar: pd.Series) -> tuple[Position, bool]:
        """Update position with current bar prices and check for close triggers.

        Returns:
            (updated_position, should_close): updated_position has unrealized_pnl set.
                should_close is True if TP/SL/max_time triggered.
        """
        bar_ts = bar.name
        if hasattr(bar_ts, "to_pydatetime"):
            bar_ts = bar_ts.to_pydatetime()

        if position.max_close_datetime is not None and bar_ts >= position.max_close_datetime:
            return position, True

        should_close = self._check_tp_sl(position, bar)
        return position, should_close

    def _check_tp_sl(self, position: Position, bar: pd.Series) -> bool:
        """Check if take-profit or stop-loss was hit."""
        high = float(bar["High"])
        low = float(bar["Low"])
        if position.direction == "long":
            tp_hit = position.take_profit is not None and high >= position.take_profit
            sl_hit = position.stop_loss is not None and low <= position.stop_loss
        else:
            tp_hit = position.take_profit is not None and low <= position.take_profit
            sl_hit = position.stop_loss is not None and high >= position.stop_loss
        return tp_hit or sl_hit

    def determine_close(
        self, position: Position, bar: pd.Series, mode: str = "conservative"
    ) -> tuple[float, str] | None:
        """Determine what triggered the close and at what price.

        Returns:
            (exit_price, close_reason) or None if no close triggered.
        """
        bar_ts = bar.name
        if hasattr(bar_ts, "to_pydatetime"):
            bar_ts = bar_ts.to_pydatetime()

        if position.max_close_datetime is not None and bar_ts >= position.max_close_datetime:
            return float(bar["Close"]), "max_time"

        high = float(bar["High"])
        low = float(bar["Low"])

        if position.direction == "long":
            tp_hit = position.take_profit is not None and high >= position.take_profit
            sl_hit = position.stop_loss is not None and low <= position.stop_loss
            if tp_hit and sl_hit:
                reason = resolve_tp_sl_conflict(position, bar, mode)
                price = position.take_profit if reason == "tp" else position.stop_loss
                return price, reason
            elif tp_hit:
                return position.take_profit, "tp"
            elif sl_hit:
                return position.stop_loss, "sl"
            else:
                return None
        else:
            tp_hit = position.take_profit is not None and low <= position.take_profit
            sl_hit = position.stop_loss is not None and high >= position.stop_loss
            if tp_hit and sl_hit:
                reason = resolve_tp_sl_conflict(position, bar, mode)
                price = position.take_profit if reason == "tp" else position.stop_loss
                return price, reason
            elif tp_hit:
                return position.take_profit, "tp"
            elif sl_hit:
                return position.stop_loss, "sl"
            else:
                return None

    def close(
        self, position: Position, exit_price: float, close_reason: str, bar_timestamp: datetime
    ) -> Position:
        """Close a position, computing exit costs and realized P&L.

        Returns:
            Closed position with exit_price, exit_datetime, realized_pnl,
            status, and close_reason set.
        """
        costs = self._cost_engine.exit_costs(
            price=exit_price,
            quantity=position.quantity,
            ticker=position.ticker,
            instrument_type=position.instrument_type,
        )
        if position.direction == "long":
            gross_pnl = (exit_price - position.entry_price) * position.quantity
        else:
            gross_pnl = (position.entry_price - exit_price) * position.quantity

        all_costs = (
            position.commission_entry
            + costs.commission
            + position.spread_cost
            + costs.spread
            + position.slippage_cost
            + costs.slippage
        )
        realized_pnl = gross_pnl - all_costs

        return position.model_copy(
            update={
                "exit_price": exit_price,
                "exit_datetime": bar_timestamp,
                "realized_pnl": realized_pnl,
                "status": "closed",
                "close_reason": close_reason,
                "commission_exit": costs.commission,
            }
        )
