import sqlite3

from phantom.errors import NotFoundError
from phantom.models.order import Order
from phantom.utils.datetime import now_utc, parse_datetime, to_iso


class OrderRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, order: Order) -> Order:
        self._conn.execute(
            """INSERT INTO orders (
                id, account_id, ticker, instrument_type, direction, order_type,
                quantity, status, limit_price, stop_price, trailing_amount, trailing_pct,
                trailing_peak, take_profit, stop_loss, created_at, triggered_at, filled_at,
                fill_price, good_til, max_close_datetime, rejection_reason, position_id,
                oco_sibling_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.id,
                order.account_id,
                order.ticker,
                order.instrument_type,
                order.direction,
                order.order_type,
                order.quantity,
                order.status,
                order.limit_price,
                order.stop_price,
                order.trailing_amount,
                order.trailing_pct,
                order.trailing_peak,
                order.take_profit,
                order.stop_loss,
                order.created_at.isoformat(),
                order.triggered_at.isoformat() if order.triggered_at else None,
                order.filled_at.isoformat() if order.filled_at else None,
                order.fill_price,
                order.good_til.isoformat() if order.good_til else None,
                order.max_close_datetime.isoformat() if order.max_close_datetime else None,
                order.rejection_reason,
                order.position_id,
                order.oco_sibling_id,
            ),
        )
        self._conn.commit()
        return order

    def get(self, order_id: str) -> Order:
        row = self._conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise NotFoundError("Order", order_id)
        return self._row_to_model(row)

    def update_status(self, order_id: str, status: str, **kwargs) -> Order:
        self.get(order_id)
        updates = {"status": status, **kwargs}
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [order_id]
        cursor = self._conn.execute(f"UPDATE orders SET {set_clause} WHERE id = ?", values)
        if cursor.rowcount == 0:
            raise NotFoundError("Order", order_id)
        self._conn.commit()
        return self.get(order_id)

    def update_prices(self, order_id: str, updates: dict) -> Order:
        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [to_iso(now_utc()), order_id]
        self._conn.execute(
            f"UPDATE orders SET {set_clauses}, updated_at = ? WHERE id = ?",
            values,
        )
        self._conn.commit()
        return self.get(order_id)

    def list_by_account(self, account_id: str, status: str | None = None) -> list[Order]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM orders WHERE account_id = ? AND status = ? ORDER BY created_at",
                (account_id, status),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM orders WHERE account_id = ? ORDER BY created_at",
                (account_id,),
            ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_pending(self) -> list[Order]:
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def _row_to_model(self, row: sqlite3.Row) -> Order:
        d = dict(row)
        for field in (
            "created_at",
            "triggered_at",
            "filled_at",
            "good_til",
            "max_close_datetime",
        ):
            if d.get(field):
                d[field] = parse_datetime(d[field])
        return Order(**d)
