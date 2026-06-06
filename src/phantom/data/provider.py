from datetime import datetime
from typing import Protocol

import pandas as pd


class DataProvider(Protocol):
    def get_bars(self, ticker: str, start: datetime, end: datetime) -> pd.DataFrame: ...

    def get_current_price(self, ticker: str) -> float: ...

    def get_bid_ask(self, ticker: str) -> tuple[float, float] | None: ...

    def get_dividends(self, ticker: str, start: datetime, end: datetime) -> list: ...
