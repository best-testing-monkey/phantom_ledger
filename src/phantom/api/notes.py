import sqlite3


class NoteAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list(self) -> list:
        return []
