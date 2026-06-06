from datetime import datetime
from pathlib import Path
import sqlite3

import pandas as pd

from phantom.data.yahoo import HistoricalProvider
from phantom.errors import DataError


class DataAPI:
    def __init__(self, conn: sqlite3.Connection, data_dir: str | Path = "./data"):
        self._conn = conn
        self._data_dir = Path(data_dir)
        self._provider = HistoricalProvider(self._data_dir)

    def fetch_prices(self, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
        try:
            return self._provider.get_bars(ticker=ticker, start=start, end=end)
        except Exception as exc:
            raise DataError(f"Failed to fetch prices for {ticker}: {exc}") from exc

    def fetch_rates(self, source: str, start: datetime, end: datetime) -> pd.DataFrame:
        raise NotImplementedError

    def list(self) -> list:
        return []
