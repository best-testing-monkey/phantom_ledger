from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path

import pandas as pd
import price_cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DividendEvent:
    """Immutable dividend event record."""

    ticker: str
    ex_date: datetime
    gross_amount: float


def get_dividends(
    ticker: str, start: datetime, end: datetime, data_dir: Path
) -> list[DividendEvent]:
    """Fetch dividend events for a ticker from price_cache.

    price_cache returns a Dividends column alongside OHLCV; rows where
    Dividends > 0 are the ex-dates. We extend the window by 90 days on
    each side so that dividends declared just outside the bar range are
    not silently dropped by gap detection.
    """
    db_path = str(data_dir / "yfd_prices.db")
    try:
        price_cache.configure(remote=False, local_mirror_path=db_path)
        df = price_cache.get_price_data(
            ticker,
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            interval="1d",
            db_path=db_path,
        )
    except Exception as exc:
        logger.error("Failed to fetch dividend data for %s: %s", ticker, exc)
        return []

    if df is None or df.empty or "Dividends" not in df.columns:
        return []

    divs = df[df["Dividends"] > 0]["Dividends"].copy()
    if divs.empty:
        return []

    if divs.index.tz is None:
        divs.index = divs.index.tz_localize("America/New_York")
    divs.index = divs.index.tz_convert("UTC")

    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    divs = divs.loc[(divs.index >= start_ts) & (divs.index <= end_ts)]

    return sorted(
        [
            DividendEvent(
                ticker=ticker,
                ex_date=ts.to_pydatetime(),
                gross_amount=float(amount),
            )
            for ts, amount in divs.items()
        ],
        key=lambda e: e.ex_date,
    )
