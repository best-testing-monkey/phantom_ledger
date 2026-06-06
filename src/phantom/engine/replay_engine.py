from datetime import datetime
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

    def replay_position(self, position: Position) -> Position:
        if position.replay_completed_at is not None:
            raise ValidationError(f"Position already replayed: {position.id}")

        end = position.max_close_datetime or now_utc()
        bars = self._data.get_bars(position.ticker, position.entry_datetime, end)

        pos = position.model_copy()
        exit_price = None
        exit_dt = None
        close_reason = None

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

        return self._apply_outcome(pos, exit_price, exit_dt, close_reason)

    def _apply_outcome(
        self,
        pos: Position,
        exit_price: float | None,
        exit_dt: datetime | None,
        close_reason: str | None,
    ) -> Position:
        if exit_price is not None:
            direction_sign = 1 if pos.direction == "long" else -1
            total_cost = (
                pos.commission_entry + pos.commission_exit + pos.spread_cost + pos.slippage_cost
            )
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
