from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DividendEvent:
    """Immutable dividend event record."""

    ticker: str
    ex_date: datetime
    gross_amount: float


def _dividend_cache_path(ticker: str, data_dir: Path) -> Path:
    """Construct dividend cache path."""
    return data_dir / "prices" / f"{ticker}_dividends.parquet"


def get_dividends(
    ticker: str, start: datetime, end: datetime, data_dir: Path
) -> list[DividendEvent]:
    """Fetch dividends from cache or live source.

    Args:
        ticker: Stock ticker symbol
        start: Start date (inclusive)
        end: End date (inclusive)
        data_dir: Base data directory

    Returns:
        List of DividendEvent objects in the date range, sorted by ex_date.
        Returns empty list if no dividends found.
    """
    cache_path = _dividend_cache_path(ticker, data_dir)

    # Try to read from cache first
    if cache_path.exists():
        try:
            df = pd.read_parquet(cache_path)
            if not df.empty:
                df["ex_date"] = pd.to_datetime(df["ex_date"], utc=True)
                mask = (df["ex_date"] >= pd.Timestamp(start, tz="UTC")) & (
                    df["ex_date"] <= pd.Timestamp(end, tz="UTC")
                )
                filtered = df.loc[mask].sort_values("ex_date")
                return [
                    DividendEvent(
                        ticker=row["ticker"],
                        ex_date=row["ex_date"].to_pydatetime(),
                        gross_amount=float(row["gross_amount"]),
                    )
                    for _, row in filtered.iterrows()
                ]
        except Exception as exc:
            logger.warning("Failed to read dividend cache for %s: %s", ticker, exc)

    # Fetch from yfinance
    try:
        import yfinance as yf

        yf_ticker = yf.Ticker(ticker)
        dividends = yf_ticker.dividends

        if dividends.empty:
            return []

        # Ensure index is tz-aware UTC
        if dividends.index.tz is None:
            dividends.index = dividends.index.tz_localize("UTC")
        else:
            dividends.index = dividends.index.tz_convert("UTC")

        # Filter to date range
        mask = (dividends.index >= pd.Timestamp(start, tz="UTC")) & (
            dividends.index <= pd.Timestamp(end, tz="UTC")
        )
        filtered = dividends.loc[mask]

        if not filtered.empty:
            # Cache the full series
            df_to_cache = pd.DataFrame(
                {
                    "ticker": ticker,
                    "ex_date": dividends.index,
                    "gross_amount": dividends.values,
                }
            )
            _write_dividend_cache(ticker, df_to_cache, data_dir)

            # Return filtered results
            results = [
                DividendEvent(
                    ticker=ticker,
                    ex_date=pd.Timestamp(ex_date).to_pydatetime(),
                    gross_amount=float(amount),
                )
                for ex_date, amount in filtered.items()
            ]
            return sorted(results, key=lambda e: e.ex_date)

        return []

    except Exception as exc:
        logger.error("Failed to fetch dividends for %s: %s", ticker, exc)
        return []


def _write_dividend_cache(ticker: str, df: pd.DataFrame, data_dir: Path) -> None:
    """Write dividend data to parquet cache."""
    path = _dividend_cache_path(ticker, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
