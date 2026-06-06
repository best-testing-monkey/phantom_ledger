import json
import sqlite3

from phantom.errors import NotFoundError
from phantom.models.account import Account
from phantom.utils.datetime import parse_datetime


class AccountRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, account: Account) -> Account:
        self._conn.execute(
            """INSERT INTO accounts (
                id, name, account_type, broker_profile_id, base_currency,
                initial_capital, cash, created_at,
                pattern_tag, algorithm_id, algorithm_version,
                algorithm_params, child_account_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account.id,
                account.name,
                account.account_type,
                account.broker_profile_id,
                account.base_currency,
                account.initial_capital,
                account.cash,
                account.created_at.isoformat(),
                account.pattern_tag,
                account.algorithm_id,
                account.algorithm_version,
                json.dumps(account.algorithm_params)
                if account.algorithm_params is not None
                else None,
                json.dumps(account.child_account_ids)
                if account.child_account_ids is not None
                else None,
            ),
        )
        self._conn.commit()
        return account

    def get(self, account_id: str) -> Account:
        row = self._conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            raise NotFoundError("Account", account_id)
        return self._row_to_model(row)

    def get_by_name(self, name: str) -> Account:
        row = self._conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise NotFoundError("Account", name)
        return self._row_to_model(row)

    def list(self, account_type: str | None = None) -> list[Account]:
        if account_type:
            rows = self._conn.execute(
                "SELECT * FROM accounts WHERE account_type = ? ORDER BY name",
                (account_type,),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM accounts ORDER BY name").fetchall()
        return [self._row_to_model(r) for r in rows]

    def update(self, account: Account) -> Account:
        cursor = self._conn.execute(
            """UPDATE accounts SET
                name=?, account_type=?, broker_profile_id=?, base_currency=?,
                initial_capital=?, cash=?, pattern_tag=?, algorithm_id=?,
                algorithm_version=?, algorithm_params=?, child_account_ids=?
            WHERE id=?""",
            (
                account.name,
                account.account_type,
                account.broker_profile_id,
                account.base_currency,
                account.initial_capital,
                account.cash,
                account.pattern_tag,
                account.algorithm_id,
                account.algorithm_version,
                json.dumps(account.algorithm_params)
                if account.algorithm_params is not None
                else None,
                json.dumps(account.child_account_ids)
                if account.child_account_ids is not None
                else None,
                account.id,
            ),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Account", account.id)
        self._conn.commit()
        return account

    def delete(self, account_id: str) -> None:
        cursor = self._conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        if cursor.rowcount == 0:
            raise NotFoundError("Account", account_id)
        self._conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> Account:
        d = dict(row)
        if d.get("algorithm_params"):
            d["algorithm_params"] = json.loads(d["algorithm_params"])
        if d.get("child_account_ids"):
            d["child_account_ids"] = json.loads(d["child_account_ids"])
        d["created_at"] = parse_datetime(d["created_at"])
        return Account(**d)
