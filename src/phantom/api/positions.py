import sqlite3

from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.models.position import Position


class PositionAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._position_repo = PositionRepo(conn)
        self._account_repo = AccountRepo(conn)

    def list(self, account_name: str | None = None, status: str | None = None) -> list[Position]:
        if account_name is None:
            return []
        account = self._account_repo.get_by_name(account_name)
        return self._position_repo.list_by_account(account.id, status=status)
