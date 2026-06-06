from datetime import datetime
import logging
from pathlib import Path

import pandas as pd
import requests

from phantom.errors import DataError

logger = logging.getLogger(__name__)


def fetch_sofr(start: datetime, end: datetime, data_dir: Path) -> pd.Series:
    """Fetch SOFR (Secured Overnight Financing Rate) from NY Fed API.

    Args:
        start: Start date
        end: End date
        data_dir: Base data directory for caching

    Returns:
        pd.Series with date index and rate values (as decimals)

    Raises:
        DataError: On network failure or parsing error
    """
    try:
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        url = (
            "https://markets.newyorkfed.org/api/rates/sofr/all/search.json"
            f"?startDate={start_str}&endDate={end_str}"
        )

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or "results" not in data or not data["results"]["observation"]:
            return pd.Series(dtype=float)

        # Parse results
        rates_data = []
        for obs in data["results"]["observation"]:
            date_str = obs.get("effectiveDate")
            rate_val = obs.get("percentRate")

            if date_str and rate_val is not None:
                try:
                    dt = pd.Timestamp(date_str, tz="UTC")
                    # Convert percentage to decimal (5.33 -> 0.0533)
                    rate = float(rate_val) / 100.0
                    rates_data.append((dt, rate))
                except (ValueError, TypeError):
                    pass

        if not rates_data:
            return pd.Series(dtype=float)

        # Create Series and cache
        series = pd.Series(
            [r[1] for r in rates_data],
            index=[r[0] for r in rates_data],
            dtype=float,
        )
        series.index.name = "date"
        series.name = "SOFR"

        _write_rate_cache("SOFR", series, data_dir)

        return series

    except requests.RequestException as exc:
        raise DataError(f"Failed to fetch SOFR from NY Fed API: {exc}") from exc
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"Failed to parse SOFR response: {exc}") from exc


def fetch_estr(start: datetime, end: datetime, data_dir: Path) -> pd.Series:
    """Fetch ESTR (Euro Short-Term Rate) from ECB SDMX API.

    Args:
        start: Start date
        end: End date
        data_dir: Base data directory for caching

    Returns:
        pd.Series with date index and rate values (as decimals)

    Raises:
        DataError: On network failure or parsing error
    """
    try:
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        url = (
            "https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT?"
            f"startPeriod={start_str}&endPeriod={end_str}&format=jsondata"
        )

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or "dataSets" not in data or not data["dataSets"]:
            return pd.Series(dtype=float)

        dataset = data["dataSets"][0]
        if "series" not in dataset:
            return pd.Series(dtype=float)

        # ECB SDMX format: series[0]["observations"][time_index] = [value]
        rates_data = []

        if dataset["series"]:
            series_key = list(dataset["series"].keys())[0]
            observations = dataset["series"][series_key].get("observations", {})

            for time_idx, obs_values in observations.items():
                if obs_values and obs_values[0] is not None:
                    try:
                        # Parse ECB time format (e.g., "2024-06-28")
                        dt = pd.Timestamp(time_idx, tz="UTC")
                        # Convert percentage to decimal
                        rate = float(obs_values[0]) / 100.0
                        rates_data.append((dt, rate))
                    except (ValueError, TypeError, IndexError):
                        pass

        if not rates_data:
            return pd.Series(dtype=float)

        series = pd.Series(
            [r[1] for r in rates_data],
            index=[r[0] for r in rates_data],
            dtype=float,
        )
        series.index.name = "date"
        series.name = "ESTR"

        _write_rate_cache("ESTR", series, data_dir)

        return series

    except requests.RequestException as exc:
        raise DataError(f"Failed to fetch ESTR from ECB API: {exc}") from exc
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise DataError(f"Failed to parse ESTR response: {exc}") from exc


def get_rate(rate_name: str, date: datetime, data_dir: Path) -> float:
    """Get reference rate for a specific date.

    Args:
        rate_name: Rate identifier (SOFR, ESTR)
        date: Target date
        data_dir: Base data directory

    Returns:
        Rate value as decimal (e.g., 0.0533 for 5.33%)

    Raises:
        DataError: If rate not found, invalid name, or cache read error
    """
    rate_name_upper = rate_name.upper()

    if rate_name_upper not in ("SOFR", "ESTR"):
        raise DataError(f"Unknown rate: {rate_name}. Supported: SOFR, ESTR")

    cache_path = data_dir / "rates" / f"{rate_name_upper}.parquet"

    # Try to read cache
    if cache_path.exists():
        try:
            df = pd.read_parquet(cache_path)
            if df.empty:
                raise DataError(f"No {rate_name} data in cache")

            # Forward-fill to handle gaps
            ts = pd.Timestamp(date, tz="UTC")
            if ts in df.index:
                return float(df.loc[ts, df.columns[0]])

            # Try to find the nearest date <= target date
            before = df.index[df.index <= ts]
            if len(before) > 0:
                return float(df.loc[before[-1], df.columns[0]])

            raise DataError(
                f"No {rate_name} data available for {date.date()}, "
                f"first available: {df.index[0].date()}"
            )

        except Exception as exc:
            if isinstance(exc, DataError):
                raise
            raise DataError(f"Failed to read {rate_name} cache: {exc}") from exc

    raise DataError(
        f"No {rate_name} data cached. Run 'phantom data fetch-rates --rate {rate_name}' first."
    )


def _write_rate_cache(rate_name: str, series: pd.Series, data_dir: Path) -> None:
    """Write rate data to parquet cache."""
    path = data_dir / "rates" / f"{rate_name}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    series.to_frame().to_parquet(path)
    logger.info("Cached %d %s data points to %s", len(series), rate_name, path)
