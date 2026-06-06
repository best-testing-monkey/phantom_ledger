from datetime import datetime
from pathlib import Path
import sqlite3

import pandas as pd

from phantom.data.rates import fetch_estr, fetch_sofr
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

    def fetch_rates(self, rate: str, start: datetime, end: datetime) -> pd.Series:
        """Fetch and cache reference rates.

        Args:
            rate: Rate name (SOFR or ESTR, case-insensitive)
            start: Start date
            end: End date

        Returns:
            pd.Series with rate data

        Raises:
            DataError: On network failure or invalid rate name
        """
        rate_upper = rate.upper()
        if rate_upper == "SOFR":
            return fetch_sofr(start, end, self._data_dir)
        elif rate_upper == "ESTR":
            return fetch_estr(start, end, self._data_dir)
        else:
            raise DataError(f"Unknown rate: {rate}. Supported: SOFR, ESTR")

    def list(self) -> list:
        return []
