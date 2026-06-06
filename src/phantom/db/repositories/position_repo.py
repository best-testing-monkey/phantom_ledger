from __future__ import annotations

from datetime import datetime
import sqlite3

from phantom.errors import NotFoundError
from phantom.models.position import Position
from phantom.utils.datetime import parse_datetime, to_iso

_UNSET = object()


class PositionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, position: Position) -> Position:
        placeholders = ", ".join("?" * 39)
        self._conn.execute(
            f"""INSERT INTO positions (
                id, account_id, ticker, instrument_type, direction,
                entry_order_id, entry_price, entry_datetime, quantity, notional,
                take_profit, stop_loss, trailing_stop_amount, trailing_stop_pct,
                trailing_stop_peak, trailing_stop_distance, peak_price, max_close_datetime,
                commission_entry, commission_exit, spread_cost, slippage_cost,
                overnight_costs, overnight_accrued, last_bar_date,
                dividend_adjustments, fx_conversion_cost, country_code,
                margin_required, leverage,
                exit_price, exit_datetime, realized_pnl, status, close_reason,
                pattern_tag, algorithm_version, replay_completed_at, created_at
            ) VALUES ({placeholders})""",
            (
                position.id,
                position.account_id,
                position.ticker,
                position.instrument_type,
                position.direction,
                position.entry_order_id,
                position.entry_price,
                position.entry_datetime.isoformat(),
                position.quantity,
                position.notional,
                position.take_profit,
                position.stop_loss,
                position.trailing_stop_amount,
                position.trailing_stop_pct,
                position.trailing_stop_peak,
                position.trailing_stop_distance,
                position.peak_price,
                position.max_close_datetime.isoformat() if position.max_close_datetime else None,
                position.commission_entry,
                position.commission_exit,
                position.spread_cost,
                position.slippage_cost,
                position.overnight_costs,
                position.overnight_accrued,
                position.last_bar_date,
                position.dividend_adjustments,
                position.fx_conversion_cost,
                position.country_code,
                position.margin_required,
                position.leverage,
                position.exit_price,
                position.exit_datetime.isoformat() if position.exit_datetime else None,
                position.realized_pnl,
                position.status,
                position.close_reason,
                position.pattern_tag,
                position.algorithm_version,
                position.replay_completed_at,
                position.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return position

    def get(self, position_id: str) -> Position:
        row = self._conn.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
        if row is None:
            raise NotFoundError("Position", position_id)
        return self._row_to_model(row)

    def list_by_account(
        self,
        account_id: str,
        status: str | None = None,
        ticker: str | None = None,
        replay_completed_at=_UNSET,
        pattern_tag: str | None = None,
        algorithm_version: str | None = None,
    ) -> list[Position]:
        query = "SELECT * FROM positions WHERE account_id = ?"
        params = [account_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        if replay_completed_at is None:
            query += " AND replay_completed_at IS NULL"
        if pattern_tag:
            query += " AND pattern_tag = ?"
            params.append(pattern_tag)
        if algorithm_version:
            query += " AND algorithm_version = ?"
            params.append(algorithm_version)
        query += " ORDER BY entry_datetime"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_open(self) -> list[Position]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE status = 'open' ORDER BY entry_datetime"
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_open_all(self) -> list[Position]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE status = 'open' ORDER BY entry_datetime"
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def update(self, position: Position) -> Position:
        cursor = self._conn.execute(
            """UPDATE positions SET
                take_profit=?, stop_loss=?, trailing_stop_peak=?, peak_price=?,
                overnight_accrued=?, last_bar_date=?, country_code=?,
                exit_price=?, exit_datetime=?, realized_pnl=?, status=?, close_reason=?,
                commission_exit=?, spread_cost=?, slippage_cost=?, overnight_costs=?,
                dividend_adjustments=?, fx_conversion_cost=?
            WHERE id=?""",
            (
                position.take_profit,
                position.stop_loss,
                position.trailing_stop_peak,
                position.peak_price,
                position.overnight_accrued,
                position.last_bar_date,
                position.country_code,
                position.exit_price,
                position.exit_datetime.isoformat() if position.exit_datetime else None,
                position.realized_pnl,
                position.status,
                position.close_reason,
                position.commission_exit,
                position.spread_cost,
                position.slippage_cost,
                position.overnight_costs,
                position.dividend_adjustments,
                position.fx_conversion_cost,
                position.id,
            ),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Position", position.id)
        self._conn.commit()
        return position

    def mark_replay_complete(self, position_id: str, dt: str | datetime) -> None:
        if not isinstance(dt, str):
            dt = to_iso(dt)
        cursor = self._conn.execute(
            "UPDATE positions SET replay_completed_at = ? WHERE id = ?",
            (dt, position_id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Position", position_id)
        self._conn.commit()

    def reset_replay(self, position_id: str) -> None:
        cursor = self._conn.execute(
            "UPDATE positions SET replay_completed_at = NULL WHERE id = ?",
            (position_id,),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Position", position_id)
        self._conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> Position:
        d = dict(row)
        for field in ("entry_datetime", "exit_datetime", "max_close_datetime", "created_at"):
            if d.get(field):
                d[field] = parse_datetime(d[field])
        return Position(**d)
