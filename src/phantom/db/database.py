from pathlib import Path
import sqlite3

from phantom.utils.datetime import now_utc, to_iso


def get_connection(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()
    applied = {row[0] for row in conn.execute("SELECT id FROM _migrations")}
    files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
    ran = []
    for f in files:
        if f.name not in applied:
            conn.executescript(f.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO _migrations (id, applied_at) VALUES (?, ?)",
                (f.name, to_iso(now_utc())),
            )
            conn.commit()
            ran.append(f.name)
    return ran
