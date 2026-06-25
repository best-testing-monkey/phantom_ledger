from datetime import datetime
import logging
from pathlib import Path

import pandas as pd
import price_cache

from phantom.data.dividends import DividendEvent, get_dividends

logger = logging.getLogger(__name__)

_configured: set[str] = set()


def _ensure_configured(db_path: str) -> None:
    if db_path not in _configured:
        price_cache.configure(remote=False, local_mirror_path=db_path)
        _configured.add(db_path)


class HistoricalProvider:
    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._db_path = str(self._data_dir / "yfd_prices.db")

    def get_bars(self, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
        _ensure_configured(self._db_path)
        try:
            df = price_cache.get_price_data(
                ticker,
                start.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d"),
                interval="1d",
                db_path=self._db_path,
            )
        except Exception as exc:
            logger.error("Failed to fetch price data for %s: %s", ticker, exc)
            return pd.DataFrame()

        if df is None or df.empty:
            # price_cache may return None when a no_data_tickers poison entry
            # was written (e.g. a fetch for today's date returned nothing), even
            # though older rows are present in the prices table.  Fall back to a
            # direct SQLite read so cached data is never silently lost.
            df = self._read_sqlite_direct(ticker, start, end)

        if df is None or df.empty:
            return pd.DataFrame()

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

        if df.index.tz is None:
            df.index = df.index.tz_localize("America/New_York")
        df.index = df.index.tz_convert("UTC")

        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC")
        return df.loc[(df.index >= start_ts) & (df.index <= end_ts)]

    def _read_sqlite_direct(self, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Direct SQLite fallback bypassing price_cache's no_data_tickers guard."""
        import sqlite3 as _sqlite3
        try:
            conn = _sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT date, open, high, low, close, volume FROM prices "
                "WHERE ticker=? AND interval_minutes=1440 AND date>=? AND date<=? "
                "ORDER BY date",
                (ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
            ).fetchall()
            conn.close()
            if not rows:
                return pd.DataFrame()
            idx = pd.to_datetime([r[0] for r in rows])
            df = pd.DataFrame(
                {"Open": [r[1] for r in rows], "High": [r[2] for r in rows],
                 "Low": [r[3] for r in rows], "Close": [r[4] for r in rows],
                 "Volume": [r[5] for r in rows]},
                index=idx,
            )
            return df
        except Exception as exc:
            logger.error("SQLite direct read failed for %s: %s", ticker, exc)
            return pd.DataFrame()

    def get_current_price(self, ticker: str) -> float:
        raise NotImplementedError("Use LiveProvider for current prices")

    def get_bid_ask(self, ticker: str) -> tuple[float, float] | None:
        return None

    def get_dividends(self, ticker: str, start: datetime, end: datetime) -> list[DividendEvent]:
        return get_dividends(ticker, start, end, self._data_dir)
