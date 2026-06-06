import sqlite3

from phantom.models.dividend_log import DividendLog


class DividendLogRepo:
    """Repository for dividend logs."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, log: DividendLog) -> DividendLog:
        """Create a new dividend log entry."""
        self._conn.execute(
            """INSERT INTO dividend_log (
                id, position_id, account_id, ex_date, dividend_per_share,
                adjustment_amount, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                log.id,
                log.position_id,
                log.account_id,
                log.ex_date,
                log.dividend_per_share,
                log.adjustment_amount,
                log.created_at,
            ),
        )
        self._conn.commit()
        return log

    def list(
        self, position_id: str | None = None, account_id: str | None = None
    ) -> list[DividendLog]:
        """List dividend logs, optionally filtered by position or account."""
        query = "SELECT * FROM dividend_log WHERE 1=1"
        params = []

        if position_id:
            query += " AND position_id = ?"
            params.append(position_id)

        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)

        query += " ORDER BY ex_date"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_model(r) for r in rows]

    def _row_to_model(self, row: sqlite3.Row) -> DividendLog:
        """Convert database row to DividendLog model."""
        d = dict(row)
        return DividendLog(**d)
