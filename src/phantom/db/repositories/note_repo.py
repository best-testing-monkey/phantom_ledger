import sqlite3

from phantom.errors import NotFoundError
from phantom.models.note import Note


class NoteRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, note: Note) -> Note:
        self._conn.execute(
            "INSERT INTO trade_notes "
            "(id, position_id, title, file_path, content_size, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                note.id,
                note.position_id,
                note.title,
                note.file_path,
                note.content_size,
                note.created_at,
                note.updated_at,
            ),
        )
        self._conn.commit()
        return note

    def get(self, note_id: str) -> Note:
        row = self._conn.execute("SELECT * FROM trade_notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise NotFoundError("Note", note_id)
        return Note(**dict(row))

    def list(self, position_id: str) -> list[Note]:
        rows = self._conn.execute(
            "SELECT * FROM trade_notes WHERE position_id = ? ORDER BY created_at ASC",
            (position_id,),
        ).fetchall()
        return [Note(**dict(r)) for r in rows]

    def update(self, note: Note) -> Note:
        cursor = self._conn.execute(
            "UPDATE trade_notes SET title = ?, content_size = ?, updated_at = ? WHERE id = ?",
            (note.title, note.content_size, note.updated_at, note.id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Note", note.id)
        self._conn.commit()
        return note

    def delete(self, note_id: str) -> None:
        cursor = self._conn.execute(
            "DELETE FROM trade_notes WHERE id = ?",
            (note_id,),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Note", note_id)
        self._conn.commit()
