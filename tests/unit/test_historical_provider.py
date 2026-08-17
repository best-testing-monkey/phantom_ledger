from datetime import datetime, timezone

import pandas as pd

from phantom.data.yahoo import HistoricalProvider


def test_get_bars_accepts_tz_aware_datetimes(tmp_path, monkeypatch):
    """parse_datetime() (used throughout the public API, e.g. ph.runner.backtest)
    always returns tz-aware UTC datetimes. get_bars must accept them without
    crashing (previously `pd.Timestamp(start, tz="UTC")` raised ValueError on
    an already tz-aware input)."""
    idx = pd.date_range("2025-01-01", periods=5, freq="D", tz="America/New_York")
    fake_df = pd.DataFrame(
        {
            "Open": [1.0, 2.0, 3.0, 4.0, 5.0],
            "High": [1.0, 2.0, 3.0, 4.0, 5.0],
            "Low": [1.0, 2.0, 3.0, 4.0, 5.0],
            "Close": [1.0, 2.0, 3.0, 4.0, 5.0],
            "Volume": [100, 100, 100, 100, 100],
            "Dividends": [0.0, 0.0, 0.0, 0.0, 0.0],
        },
        index=idx,
    )

    monkeypatch.setattr("phantom.data.yahoo.price_cache.get_price_data", lambda *a, **k: fake_df)
    monkeypatch.setattr("phantom.data.yahoo.price_cache.configure", lambda *a, **k: None)

    provider = HistoricalProvider(data_dir=str(tmp_path))
    start = datetime(2025, 1, 2, tzinfo=timezone.utc)
    end = datetime(2025, 1, 4, tzinfo=timezone.utc)

    result = provider.get_bars("AAPL", start, end)

    assert not result.empty
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert result.index.min() >= pd.Timestamp(start)
    assert result.index.max() <= pd.Timestamp(end)
