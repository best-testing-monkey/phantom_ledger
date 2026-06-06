from datetime import datetime
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
