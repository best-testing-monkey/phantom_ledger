from datetime import date
from pathlib import Path

import pandas as pd


def _cache_path(ticker: str, data_dir: Path) -> Path:
    return data_dir / "prices" / f"{ticker}.parquet"


def is_cache_fresh(ticker: str, data_dir: Path) -> bool:
    path = _cache_path(ticker, data_dir)
    if not path.exists():
        return False
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return False
        last_date = df.index.max().date()
        return last_date >= date.today()
    except Exception:
        return False


def read_cache(ticker: str, data_dir: Path) -> pd.DataFrame | None:
    path = _cache_path(ticker, data_dir)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def write_cache(ticker: str, df: pd.DataFrame, data_dir: Path) -> None:
    path = _cache_path(ticker, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def append_bars(ticker: str, new_df: pd.DataFrame, data_dir: Path) -> None:
    existing = read_cache(ticker, data_dir)
    if existing is None or existing.empty:
        write_cache(ticker, new_df, data_dir)
        return
    combined = pd.concat([existing, new_df])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()
    write_cache(ticker, combined, data_dir)
