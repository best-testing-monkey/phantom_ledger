import logging
from pathlib import Path
import sqlite3

from phantom.db.repositories.note_repo import NoteRepo
from phantom.errors import DataError, ValidationError
from phantom.models.note import Note
from phantom.utils.datetime import now_utc, to_iso
from phantom.utils.ids import new_id

logger = logging.getLogger(__name__)

SIZE_WARNING_THRESHOLD = 4_500_000


class NoteManager:
    def __init__(self, data_dir: Path, conn: sqlite3.Connection) -> None:
        self._data_dir = Path(data_dir)
        self._repo = NoteRepo(conn)

    def _track_size(self, note_id: str, content: str) -> int:
        size = len(content.encode("utf-8"))
        if size > SIZE_WARNING_THRESHOLD:
            logger.warning(
                "Note %s approaching 5 MB limit: current size %d bytes",
                note_id,
                size,
            )
        return size

    def create(self, position_id: str, account_id: str, title: str, content: str) -> Note:
        note_id = new_id()
        content_size = self._track_size(note_id, content)
        rel_path = f"notes/{account_id}/{position_id}/{note_id}.md"
        abs_path = self._data_dir / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
        now = to_iso(now_utc())
        note = Note(
            id=note_id,
            position_id=position_id,
            account_id=account_id,
            title=title,
            file_path=rel_path,
            content_size=content_size,
            created_at=now,
            updated_at=now,
        )
        return self._repo.create(note)

    def create_from_file(
        self, position_id: str, account_id: str, title: str, source_path: str
    ) -> Note:
        path = Path(source_path)
        if not path.exists():
            raise DataError(f"Note source file not found: {path}")
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            raise ValidationError("Note file is empty")
        return self.create(position_id, account_id, title, content)

    def read(self, note_id: str) -> str:
        note = self._repo.get(note_id)
        abs_path = self._data_dir / note.file_path
        if not abs_path.exists():
            raise DataError(f"Note file missing from disk: {abs_path}")
        return abs_path.read_text(encoding="utf-8")

    def list(self, position_id: str) -> list[Note]:
        return self._repo.list(position_id)
