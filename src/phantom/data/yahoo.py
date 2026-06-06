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
            return pd.DataFrame()

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

        if df.index.tz is None:
            df.index = df.index.tz_localize("America/New_York")
        df.index = df.index.tz_convert("UTC")

        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC")
        return df.loc[(df.index >= start_ts) & (df.index <= end_ts)]

    def get_current_price(self, ticker: str) -> float:
        raise NotImplementedError("Use LiveProvider for current prices")

    def get_bid_ask(self, ticker: str) -> tuple[float, float] | None:
        return None

    def get_dividends(self, ticker: str, start: datetime, end: datetime) -> list[DividendEvent]:
        return get_dividends(ticker, start, end, self._data_dir)
