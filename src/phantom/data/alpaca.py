from datetime import datetime
import logging
import os
from pathlib import Path

import pandas as pd
import requests

from phantom.data.yahoo import HistoricalProvider
from phantom.errors import DataError

logger = logging.getLogger(__name__)


class LiveProvider:
    """Live data provider using yfinance quotes and Alpaca market data API.

    Falls back to HistoricalProvider for bars. Gracefully returns None/empty
    for live data if APIs are unavailable or not configured.
    """

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._historical = HistoricalProvider(self._data_dir)
        self._alpaca_key = os.environ.get("ALPACA_API_KEY")
        self._alpaca_secret = os.environ.get("ALPACA_SECRET_KEY")

    def get_bars(self, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Delegate to HistoricalProvider."""
        return self._historical.get_bars(ticker=ticker, start=start, end=end)

    def get_current_price(self, ticker: str) -> float:
        """Get latest price from yfinance.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Latest closing price

        Raises:
            DataError: On network failure or if data unavailable
        """
        try:
            import yfinance as yf

            yf_ticker = yf.Ticker(ticker)
            hist = yf_ticker.history(period="1d")
            if hist.empty:
                raise DataError(f"No price data available for {ticker}")
            return float(hist["Close"].iloc[-1])
        except Exception as exc:
            raise DataError(f"Failed to fetch current price for {ticker}: {exc}") from exc

    def get_bid_ask(self, ticker: str) -> tuple[float, float] | None:
        """Get latest bid/ask from Alpaca market data API.

        Returns None if API is not configured or data unavailable (non-error).

        Args:
            ticker: Stock ticker symbol

        Returns:
            Tuple of (bid, ask) prices, or None if unavailable
        """
        if not self._alpaca_key or not self._alpaca_secret:
            logger.debug(
                "Alpaca API not configured (ALPACA_API_KEY/ALPACA_SECRET_KEY env vars). "
                "Returning None for bid/ask."
            )
            return None

        try:
            url = f"https://data.alpaca.markets/v2/stocks/{ticker}/quotes/latest"
            headers = {
                "APCA-API-KEY-ID": self._alpaca_key,
            }
            params = {"feed": "sip"}

            response = requests.get(url, headers=headers, params=params, timeout=5)

            if response.status_code == 404:
                logger.debug("Quote not found for %s on Alpaca", ticker)
                return None

            response.raise_for_status()
            data = response.json()

            if not data or "quote" not in data:
                return None

            quote = data["quote"]
            bid = quote.get("bp")  # bid price
            ask = quote.get("ap")  # ask price

            if bid is not None and ask is not None:
                return (float(bid), float(ask))

            return None

        except requests.RequestException as exc:
            logger.warning("Failed to fetch bid/ask from Alpaca for %s: %s", ticker, exc)
            return None
        except Exception as exc:
            logger.warning("Error parsing Alpaca bid/ask response for %s: %s", ticker, exc)
            return None

    def get_dividends(self, ticker: str, start: datetime, end: datetime) -> list:
        """Delegate to HistoricalProvider."""
        return self._historical.get_dividends(ticker=ticker, start=start, end=end)
