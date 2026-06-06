import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from phantom.data.dividends import DividendEvent, get_dividends
from phantom.data.price_store import is_cache_fresh, read_cache, write_cache

logger = logging.getLogger(__name__)


class HistoricalProvider:
    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)

    def get_bars(self, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
        if is_cache_fresh(ticker, self._data_dir):
            cached = read_cache(ticker, self._data_dir)
            if cached is not None:
                mask = (cached.index >= pd.Timestamp(start, tz="UTC")) & (
                    cached.index <= pd.Timestamp(end, tz="UTC")
                )
                return cached.loc[mask]
        try:
            import yfinance as yf

            df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        except Exception as exc:
            logger.error("Failed to fetch price data for %s: %s", ticker, exc)
            return pd.DataFrame()
        if df.empty:
            return df
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        write_cache(ticker, df, self._data_dir)
        return df

    def get_current_price(self, ticker: str) -> float:
        raise NotImplementedError("Use LiveProvider for current prices")

    def get_bid_ask(self, ticker: str) -> tuple[float, float] | None:
        return None

    def get_dividends(self, ticker: str, start: datetime, end: datetime) -> list[DividendEvent]:
        return get_dividends(ticker, start, end, self._data_dir)
