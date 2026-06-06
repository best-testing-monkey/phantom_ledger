import sqlite3

from phantom.models.equity_point import EquityPoint


class EquityRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, point: EquityPoint) -> EquityPoint:
        self._conn.execute(
            "INSERT INTO equity_curve "
            "(id, account_id, timestamp, equity, cash, unrealized_pnl, used_margin, drawdown_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                point.id,
                point.account_id,
                point.timestamp,
                point.equity,
                point.cash,
                point.unrealized_pnl,
                point.used_margin,
                point.drawdown_pct,
            ),
        )
        self._conn.commit()
        return point

    def list(self, account_id: str) -> list[EquityPoint]:
        rows = self._conn.execute(
            "SELECT * FROM equity_curve WHERE account_id = ? ORDER BY timestamp ASC",
            (account_id,),
        ).fetchall()
        return [EquityPoint(**dict(row)) for row in rows]
