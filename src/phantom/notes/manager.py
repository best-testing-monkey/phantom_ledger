from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class SearchResult:
    file_path: str
    line_number: int
    line: str


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

    def update(self, note_id: str, content: str) -> Note:
        note = self._repo.get(note_id)
        abs_path = self._data_dir / note.file_path
        abs_path.write_text(content, encoding="utf-8")
        content_size = self._track_size(note_id, content)
        updated_note = Note(
            id=note.id,
            position_id=note.position_id,
            account_id=note.account_id,
            title=note.title,
            file_path=note.file_path,
            content_size=content_size,
            created_at=note.created_at,
            updated_at=to_iso(now_utc()),
        )
        return self._repo.update(updated_note)

    def search(self, account_id: str, keyword: str) -> list[SearchResult]:
        notes_dir = self._data_dir / "notes" / account_id
        if not notes_dir.exists():
            return []
        results = []
        keyword_lower = keyword.lower()
        for md_file in notes_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                for line_number, line in enumerate(content.split("\n"), start=1):
                    if keyword_lower in line.lower():
                        results.append(
                            SearchResult(
                                file_path=str(md_file.relative_to(self._data_dir)),
                                line_number=line_number,
                                line=line,
                            )
                        )
            except Exception as e:
                logger.warning("Error searching file %s: %s", md_file, e)
        return results
