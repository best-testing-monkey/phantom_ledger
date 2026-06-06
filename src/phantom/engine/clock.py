from datetime import datetime, timezone
import time
from typing import Protocol

import pandas as pd

from phantom.utils.datetime import parse_datetime


class Clock(Protocol):
    def now(self) -> datetime: ...
    def advance(self) -> None: ...
    def is_done(self) -> bool: ...


class BacktestClock:
    def __init__(self, index: pd.DatetimeIndex) -> None:
        self._index = index
        self._pos = 0

    def now(self) -> datetime:
        if self._pos >= len(self._index):
            raise StopIteration("BacktestClock exhausted")
        return parse_datetime(self._index[self._pos].to_pydatetime())

    def advance(self) -> None:
        self._pos += 1

    def is_done(self) -> bool:
        return self._pos >= len(self._index)


class LiveClock:
    """Wall-clock based clock for paper trading.

    Returns current UTC time and sleeps until the next tick interval.
    """

    def __init__(self, interval: float) -> None:
        """Initialize LiveClock.

        Args:
            interval: Interval in seconds between ticks.
        """
        self._interval = interval
        self._last_tick = time.monotonic()

    def now(self) -> datetime:
        """Return current UTC time."""
        return datetime.now(timezone.utc)

    def advance(self) -> None:
        """Sleep until the next tick interval."""
        elapsed = time.monotonic() - self._last_tick
        sleep_for = max(0.0, self._interval - elapsed)
        time.sleep(sleep_for)
        self._last_tick = time.monotonic()

    def is_done(self) -> bool:
        """Paper trading loop never finishes; only stops on external signal."""
        return False
