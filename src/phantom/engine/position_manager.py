from datetime import datetime
import logging

import pandas as pd

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.dividend_log_repo import DividendLogRepo
from phantom.db.repositories.overnight_log_repo import OvernightLogRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.models.dividend_log import DividendLog
from phantom.models.overnight_log import OvernightLog
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
        self,
        position_repo: PositionRepo,
        account_repo: AccountRepo,
        cost_engine: CostEngine,
        overnight_log_repo: OvernightLogRepo | None = None,
        dividend_log_repo: DividendLogRepo | None = None,
    ):
        self._position_repo = position_repo
        self._account_repo = account_repo
        self._cost_engine = cost_engine
        self._overnight_log_repo = overnight_log_repo
        self._dividend_log_repo = dividend_log_repo

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

    def _update_trailing_stop(self, position: Position, bar: pd.Series) -> bool:
        """Update trailing stop peak and check if triggered.

        Args:
            position: The position to update
            bar: Price bar with Open/High/Low/Close

        Returns:
            True if trailing stop should trigger a close
        """
        if position.trailing_stop_distance is None:
            return False

        high = float(bar["High"])
        low = float(bar["Low"])
        close = float(bar["Close"])

        if position.direction == "long":
            new_peak = max(position.peak_price or position.entry_price, high)
            position.peak_price = new_peak
            return new_peak - close >= position.trailing_stop_distance
        else:
            new_peak = min(position.peak_price or position.entry_price, low)
            position.peak_price = new_peak
            return close - new_peak >= position.trailing_stop_distance

    def _apply_overnight_cost(
        self,
        position: Position,
        account,
        bar: pd.Series,
        overnight_model,
        reference_rate: float,
    ) -> None:
        """Apply overnight financing charge to CFD position.

        Args:
            position: The position
            account: The account (will be modified)
            bar: Price bar (contains date info via index)
            overnight_model: OvernightModel from broker profile
            reference_rate: Current reference rate (SOFR, ESTR, etc.)
        """
        if position.instrument_type != "cfd":
            return

        # Extract bar date
        bar_ts = bar.name
        if hasattr(bar_ts, "to_pydatetime"):
            bar_ts = bar_ts.to_pydatetime()

        bar_date = bar_ts.strftime("%Y-%m-%d") if isinstance(bar_ts, datetime) else str(bar_ts)
        day_of_week = bar_ts.weekday() if hasattr(bar_ts, "weekday") else 0

        # Skip if we haven't crossed a day boundary
        if position.last_bar_date == bar_date:
            return

        # Calculate charge using overnight model
        charge = overnight_model.calculate(
            position.notional, position.direction, reference_rate, day_of_week
        )

        if charge > 0:
            position.overnight_accrued += charge
            account.cash -= charge

            # Persist log if repo is available
            if self._overnight_log_repo:
                log = OvernightLog(
                    position_id=position.id,
                    account_id=account.id,
                    date=bar_date,
                    rate=reference_rate,
                    charge_amount=charge,
                )
                self._overnight_log_repo.create(log)

            logger.debug(
                "Applied overnight cost %s to position %s, day_of_week=%s",
                charge,
                position.id,
                day_of_week,
            )

        position.last_bar_date = bar_date

    def _apply_dividend(
        self, position: Position, account, bar_date: str, dividend_model, data_provider, data_dir
    ) -> float:
        """Apply dividend adjustment to position.

        Args:
            position: The position
            account: The account (will be modified)
            bar_date: Current bar date as ISO string
            dividend_model: DividendModel from broker profile
            data_provider: DataProvider instance
            data_dir: Data directory path

        Returns:
            Adjustment amount (may be positive or negative)
        """
        from datetime import datetime as dt

        from phantom.data.dividends import get_dividends

        # Parse bar_date
        bar_dt = dt.fromisoformat(bar_date.replace("Z", "+00:00"))

        # Get dividends for this ticker on this date
        dividends = get_dividends(position.ticker, bar_dt, bar_dt, data_dir)

        if not dividends:
            return 0.0

        dividend_event = dividends[0]
        dividend_per_share = dividend_event.gross_amount

        # Calculate adjustment based on instrument type
        if position.instrument_type == "stock":
            withholding_rate = dividend_model.withholding_rates.get(
                position.country_code or "US", 0.0
            )
            gross = dividend_per_share * position.quantity
            adjustment = gross * (1 - withholding_rate)
        elif position.direction == "long":
            gross = dividend_per_share * position.quantity
            adjustment = gross * dividend_model.cfd_dividend_adjustment
        else:  # short CFD
            gross = dividend_per_share * position.quantity
            adjustment = -(gross * dividend_model.cfd_short_dividend_charge)

        if adjustment != 0:
            account.cash += adjustment
            position.dividend_adjustments += adjustment

            # Persist log if repo is available
            if self._dividend_log_repo:
                log = DividendLog(
                    position_id=position.id,
                    account_id=account.id,
                    ex_date=bar_date,
                    dividend_per_share=dividend_per_share,
                    adjustment_amount=adjustment,
                )
                self._dividend_log_repo.create(log)

            logger.debug(
                "Applied dividend adjustment %s to position %s, dividend_per_share=%s",
                adjustment,
                position.id,
                dividend_per_share,
            )

        return adjustment

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
        close = float(bar["Close"])

        # Check trailing stop
        if position.trailing_stop_distance is not None:
            if position.direction == "long":
                new_peak = max(position.peak_price or position.entry_price, high)
                if new_peak - close >= position.trailing_stop_distance:
                    return close, "trailing_stop"
            else:
                new_peak = min(position.peak_price or position.entry_price, low)
                if close - new_peak >= position.trailing_stop_distance:
                    return close, "trailing_stop"

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
