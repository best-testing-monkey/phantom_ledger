import sqlite3


class ReportAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list(self) -> list:
        return []
