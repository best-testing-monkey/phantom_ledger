from dataclasses import dataclass
from datetime import date, datetime
import logging

import pandas as pd

from phantom.costs.engine import CostEngine
from phantom.data.provider import DataProvider
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.position_manager import resolve_tp_sl_conflict
from phantom.errors import ValidationError
from phantom.models.position import Position
from phantom.utils.datetime import now_utc, to_iso

logger = logging.getLogger(__name__)


@dataclass
class MarginCallEvent:
    account_id: str
    position_id: str
    bar_timestamp: datetime
    margin_level: float
    close_price: float


class ReplayEngine:
    def __init__(
        self,
        data_provider: DataProvider,
        cost_engine: CostEngine,
        position_repo: PositionRepo,
    ) -> None:
        self._data = data_provider
        self._costs = cost_engine
        self._repo = position_repo
        self._price_cache: dict[tuple[str, date, date], pd.DataFrame] = {}

    def _get_bars_cached(self, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Get bars from cache or fetch and cache them.

        Args:
            ticker: Stock ticker symbol
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with OHLCV data
        """
        start_date = start.date() if hasattr(start, "date") else start
        end_date = end.date() if hasattr(end, "date") else end
        key = (ticker, start_date, end_date)

        if key in self._price_cache:
            logger.debug("Cache hit for %s [%s, %s]", ticker, start_date, end_date)
            return self._price_cache[key]

        bars = self._data.get_bars(ticker, start, end)
        self._price_cache[key] = bars
        return bars

    def _apply_overnight(self, pos: Position, bar_date: date, notional: float) -> float:
        """Compute overnight charge using broker overnight model.

        Args:
            pos: Position to charge
            bar_date: Current bar date
            notional: Notional value of position

        Returns:
            Overnight charge amount (positive = cost)
        """
        # Get the reference rate and day of week info
        # For simplicity, use a fixed reference rate (0% baseline)
        reference_rate = 0.0
        day_of_week = bar_date.weekday()  # 0=Monday, 4=Friday, 2=Wednesday

        charge = self._costs._profile.overnight.calculate(
            notional=notional,
            direction=pos.direction,
            reference_rate=reference_rate,
            day_of_week=day_of_week,
        )

        logger.debug("Overnight charge %s %.4f", bar_date, charge)
        return charge

    def _apply_dividend(self, pos: Position, bar_date: date, ex_dates: dict[date, float]) -> float:
        """Apply dividend adjustment if bar_date is in ex_dates.

        Args:
            pos: Position to adjust
            bar_date: Current bar date
            ex_dates: Dictionary mapping ex-date (date) to dividend per share

        Returns:
            Dividend adjustment amount (positive = cash in, negative = cash out)
        """
        if bar_date not in ex_dates:
            return 0.0

        div_per_share = ex_dates[bar_date]

        if pos.direction == "long":
            amount = div_per_share * pos.quantity
        else:
            # Short position: lose the dividend, pay short dividend charge
            cfd_short_charge = self._costs._profile.dividend.cfd_short_dividend_charge
            amount = -(div_per_share * pos.quantity * cfd_short_charge)

        logger.info("Dividend event %s amount=%.4f", bar_date, amount)
        return amount

    def _check_margin(
        self,
        pos: Position,
        margin_engine,
        equity: float,
        used_margin: float,
        bar_close: float,
        bar_ts: datetime,
    ) -> MarginCallEvent | None:
        """Check margin status and return event if stop-out triggered.

        Args:
            pos: Position to check
            margin_engine: MarginEngine instance
            equity: Current account equity (cash)
            used_margin: Total used margin
            bar_close: Close price at current bar
            bar_ts: Current bar timestamp

        Returns:
            MarginCallEvent if stop-out triggered, else None
        """
        # Compute margin level directly
        if used_margin == 0:
            margin_level = float("inf")
        else:
            margin_level = (equity / used_margin) * 100

        stop_out_level = self._costs._profile.margin.stop_out_level

        if margin_level <= stop_out_level:
            logger.warning(
                "Stop-out triggered for %s at margin_level=%.2f%%",
                pos.id,
                margin_level,
            )
            return MarginCallEvent(
                account_id=pos.account_id,
                position_id=pos.id,
                bar_timestamp=bar_ts,
                margin_level=margin_level,
                close_price=bar_close,
            )

        return None

    def replay_position(self, position: Position) -> Position:
        if position.replay_completed_at is not None:
            raise ValidationError(f"Position already replayed: {position.id}")

        end = position.max_close_datetime or now_utc()
        bars = self._get_bars_cached(position.ticker, position.entry_datetime, end)

        pos = position.model_copy()
        exit_price = None
        exit_dt = None
        close_reason = None

        # Fetch dividends for the entire period
        dividend_events = self._data.get_dividends(position.ticker, position.entry_datetime, end)
        ex_dates = {event.ex_date.date(): event.gross_amount for event in dividend_events}

        prev_bar_date = None
        total_cost = 0.0

        for bar in bars.itertuples():
            close_price = float(bar.Close)
            high = float(bar.High)
            low = float(bar.Low)

            logger.debug(
                "Replay bar %s %s close=%.4f",
                pos.ticker,
                bar.Index,
                close_price,
            )

            bar_ts = bar.Index
            if hasattr(bar_ts, "to_pydatetime"):
                bar_ts = bar_ts.to_pydatetime()

            bar_date = bar_ts.date() if hasattr(bar_ts, "date") else bar_ts

            # Apply overnight charge on day boundary
            if prev_bar_date is not None and prev_bar_date != bar_date:
                notional = pos.entry_price * pos.quantity
                overnight_charge = self._apply_overnight(pos, bar_date, notional)
                total_cost += overnight_charge

            # Apply dividend adjustment on each bar
            div_adjustment = self._apply_dividend(pos, bar_date, ex_dates)
            total_cost += div_adjustment

            # Check margin for CFD positions
            if pos.instrument_type == "cfd":
                from phantom.engine.margin_engine import MarginEngine

                margin_engine = MarginEngine()
                notional = close_price * pos.quantity
                used_margin = notional * self._costs._profile.margin.default_margin_pct
                # Assume simple equity model: cash is only constraint
                equity = 10000.0  # Placeholder; in real usage, need account cash
                margin_event = self._check_margin(
                    pos, margin_engine, equity, used_margin, close_price, bar_ts
                )
                if margin_event is not None:
                    exit_price = close_price
                    exit_dt = bar_ts
                    close_reason = "margin_call"
                    break

            if pos.max_close_datetime is not None and bar_ts >= pos.max_close_datetime:
                exit_price = close_price
                exit_dt = bar_ts
                close_reason = "max_time"
                break

            if pos.direction == "long":
                tp_hit = pos.take_profit is not None and high >= pos.take_profit
                sl_hit = pos.stop_loss is not None and low <= pos.stop_loss
            else:
                tp_hit = pos.take_profit is not None and low <= pos.take_profit
                sl_hit = pos.stop_loss is not None and high >= pos.stop_loss

            if tp_hit and sl_hit:
                bar_series = pd.Series(
                    {
                        "Open": float(bar.Open),
                        "High": float(bar.High),
                        "Low": float(bar.Low),
                        "Close": close_price,
                    }
                )
                reason = resolve_tp_sl_conflict(pos, bar_series, "conservative")
                if reason == "tp":
                    exit_price = pos.take_profit
                    close_reason = "tp"
                else:
                    exit_price = pos.stop_loss
                    close_reason = "sl"
                exit_dt = bar_ts
                break
            elif tp_hit:
                exit_price = pos.take_profit
                exit_dt = bar_ts
                close_reason = "tp"
                break
            elif sl_hit:
                exit_price = pos.stop_loss
                exit_dt = bar_ts
                close_reason = "sl"
                break

            prev_bar_date = bar_date

        return self._apply_outcome(pos, exit_price, exit_dt, close_reason, total_cost)

    def _apply_outcome(
        self,
        pos: Position,
        exit_price: float | None,
        exit_dt: datetime | None,
        close_reason: str | None,
        accumulated_costs: float = 0.0,
    ) -> Position:
        if exit_price is not None:
            direction_sign = 1 if pos.direction == "long" else -1
            entry_and_exit_costs = (
                pos.commission_entry + pos.commission_exit + pos.spread_cost + pos.slippage_cost
            )
            total_cost = entry_and_exit_costs + accumulated_costs
            realized_pnl = (
                exit_price - pos.entry_price
            ) * pos.quantity * direction_sign - total_cost
            pos = pos.model_copy(
                update={
                    "status": "closed",
                    "close_reason": close_reason,
                    "exit_price": exit_price,
                    "exit_datetime": exit_dt,
                    "realized_pnl": realized_pnl,
                    "overnight_costs": accumulated_costs,
                    "replay_completed_at": to_iso(now_utc()),
                }
            )
            logger.info(
                "Replay closed %s via %s at %.4f pnl=%.2f",
                pos.ticker,
                close_reason,
                exit_price,
                realized_pnl,
            )
        else:
            pos = pos.model_copy(update={"replay_completed_at": to_iso(now_utc())})

        self._repo.update(pos)
        return pos
