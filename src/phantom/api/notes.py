from __future__ import annotations

from pathlib import Path
import sqlite3

from phantom.db.repositories.note_repo import NoteRepo
from phantom.models.note import Note
from phantom.notes.manager import NoteManager, SearchResult


class NoteAPI:
    def __init__(self, conn: sqlite3.Connection, data_dir: str | Path = "./data"):
        self._data_dir = Path(data_dir)
        self._manager = NoteManager(self._data_dir, conn)
        self._repo = NoteRepo(conn)

    def create(self, position_id: str, account_id: str, title: str, content: str) -> Note:
        return self._manager.create(position_id, account_id, title, content)

    def create_from_file(
        self, position_id: str, account_id: str, title: str, source_path: str
    ) -> Note:
        return self._manager.create_from_file(position_id, account_id, title, source_path)

    def read(self, note_id: str) -> str:
        return self._manager.read(note_id)

    def list(self, position_id: str) -> list[Note]:
        return self._manager.list(position_id)

    def get(self, note_id: str) -> Note:
        return self._repo.get(note_id)

    def update(self, note_id: str, content: str) -> Note:
        return self._manager.update(note_id, content)

    def search(self, account_id: str, keyword: str) -> list[SearchResult]:
        return self._manager.search(account_id, keyword)

    def add(
        self, position_id: str, account_id: str, content: str, title: str | None = None
    ) -> Note:
        return self.create(
            position_id=position_id,
            account_id=account_id,
            title=title or "",
            content=content,
        )

    def delete(self, note_id: str) -> None:
        return self._manager.delete(note_id)
