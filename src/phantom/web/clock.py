"""File-backed simulated clock store for the web UI."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from phantom.config import get_data_dir

_CLOCK_FILE = Path(get_data_dir()) / "web_clock.json"


def get_simulated_now() -> datetime | None:
    """Get the current simulated datetime, or None if not set."""
    if not _CLOCK_FILE.exists():
        return None
    raw = json.loads(_CLOCK_FILE.read_text())
    return datetime.fromisoformat(raw["simulated_now"])


def set_simulated_now(dt: datetime) -> datetime:
    """Set the simulated datetime to the given value. Ensures UTC timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    _CLOCK_FILE.write_text(json.dumps({"simulated_now": dt.isoformat()}))
    return dt


def step_simulated_now(days: int) -> datetime:
    """Step the simulated clock forward or backward by N days."""
    current = get_simulated_now() or datetime.now(timezone.utc)
    return set_simulated_now(current + timedelta(days=days))
