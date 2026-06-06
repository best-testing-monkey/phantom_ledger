import sqlite3

from phantom.models.overnight_log import OvernightLog


class OvernightLogRepo:
    """Repository for overnight financing logs."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, log: OvernightLog) -> OvernightLog:
        """Create a new overnight log entry."""
        self._conn.execute(
            """INSERT INTO overnight_log (
                id, position_id, account_id, date, rate, charge_amount, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                log.id,
                log.position_id,
                log.account_id,
                log.date,
                log.rate,
                log.charge_amount,
                log.created_at,
            ),
        )
        self._conn.commit()
        return log

    def list(
        self, position_id: str | None = None, account_id: str | None = None
    ) -> list[OvernightLog]:
        """List overnight logs, optionally filtered by position or account."""
        query = "SELECT * FROM overnight_log WHERE 1=1"
        params = []

        if position_id:
            query += " AND position_id = ?"
            params.append(position_id)

        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)

        query += " ORDER BY date"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_model(r) for r in rows]

    def _row_to_model(self, row: sqlite3.Row) -> OvernightLog:
        """Convert database row to OvernightLog model."""
        d = dict(row)
        return OvernightLog(**d)
