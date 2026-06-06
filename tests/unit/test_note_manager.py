import logging

import pytest

from phantom.notes.manager import NoteManager
from phantom.utils.datetime import now_utc, to_iso
from phantom.utils.ids import new_id


@pytest.fixture
def note_manager_setup(tmp_path, db_conn):
    aid = new_id()
    bid = new_id()
    oid = new_id()
    pid = new_id()

    now = to_iso(now_utc())
    db_conn.execute(
        "INSERT INTO broker_profiles "
        "(id, name, config_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (bid, "TEST", "{}", now, now),
    )
    db_conn.execute(
        "INSERT INTO accounts "
        "(id, name, account_type, broker_profile_id, "
        "base_currency, initial_capital, cash, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, "acct", "manual", bid, "EUR", 10000.0, 10000.0, now),
    )
    db_conn.execute(
        "INSERT INTO orders "
        "(id, account_id, ticker, instrument_type, direction, "
        "order_type, quantity, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (oid, aid, "AAPL", "stock", "long", "market", 10.0, "filled", now),
    )
    db_conn.execute(
        "INSERT INTO positions "
        "(id, account_id, ticker, instrument_type, direction, "
        "entry_order_id, entry_price, entry_datetime, "
        "quantity, notional, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pid, aid, "AAPL", "stock", "long", oid, 185.0, now, 10.0, 1850.0, "open", now),
    )
    db_conn.commit()
    manager = NoteManager(tmp_path, db_conn)
    return manager, pid, aid


class TestNoteManager:
    def test_create_note(self, note_manager_setup):
        manager, pid, aid = note_manager_setup
        note = manager.create(pid, aid, "My Trade Note", "# Analysis\n\nThis is my note.")
        assert note.title == "My Trade Note"
        assert note.content_size == len("# Analysis\n\nThis is my note.".encode("utf-8"))
        assert note.position_id == pid
        assert note.account_id == aid

    def test_read_note(self, note_manager_setup):
        manager, pid, aid = note_manager_setup
        note = manager.create(pid, aid, "Test Note", "Content here")
        content = manager.read(note.id)
        assert content == "Content here"

    def test_list_notes(self, note_manager_setup):
        manager, pid, aid = note_manager_setup
        manager.create(pid, aid, "Note 1", "Content 1")
        manager.create(pid, aid, "Note 2", "Content 2")
        notes = manager.list(pid)
        assert len(notes) == 2

    def test_size_warning_logged(self, note_manager_setup, caplog):
        manager, pid, aid = note_manager_setup
        big_content = "x" * 5_000_000
        with caplog.at_level(logging.WARNING, logger="phantom.notes.manager"):
            manager.create(pid, aid, "Big Note", big_content)
        assert any("approaching 5 MB limit" in r.message for r in caplog.records)

    def test_create_from_file(self, note_manager_setup, tmp_path):
        manager, pid, aid = note_manager_setup
        source_file = tmp_path / "source.md"
        source_file.write_text("File content", encoding="utf-8")
        note = manager.create_from_file(pid, aid, "From File", str(source_file))
        assert note.title == "From File"
        content = manager.read(note.id)
        assert content == "File content"

    def test_create_from_nonexistent_file(self, note_manager_setup):
        manager, pid, aid = note_manager_setup
        from phantom.errors import DataError

        with pytest.raises(DataError, match="not found"):
            manager.create_from_file(pid, aid, "Test", "/nonexistent/path.md")

    def test_create_from_empty_file(self, note_manager_setup, tmp_path):
        manager, pid, aid = note_manager_setup
        from phantom.errors import ValidationError

        source_file = tmp_path / "empty.md"
        source_file.write_text("", encoding="utf-8")
        with pytest.raises(ValidationError, match="empty"):
            manager.create_from_file(pid, aid, "Empty", str(source_file))
