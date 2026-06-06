import logging

try:
    import pandas as pd
except ImportError:
    pd = None

logger = logging.getLogger(__name__)


def combine_equity_curves(curves: list) -> object:
    """
    Combine multiple equity curve Series into a single aggregated Series.

    Aligns all curves on their common DatetimeIndex (outer join) and forward-fills
    NaN values, then sums equity values at each timestamp.

    Args:
        curves: List of pandas Series with DatetimeIndex

    Returns:
        Aggregated pandas Series with combined equity values
    """
    if pd is None:
        raise ImportError("pandas is required for equity_curve operations")
    if not curves:
        return pd.Series(dtype=float)
    if len(curves) == 1:
        return curves[0].copy()

    # Outer join all indices to get the union of all timestamps
    combined = None
    for curve in curves:
        if curve is None or curve.empty:
            continue
        if combined is None:
            combined = pd.DataFrame({0: curve})
        else:
            combined = combined.join(pd.DataFrame({len(combined.columns): curve}), how="outer")

    if combined is None or combined.empty:
        return pd.Series(dtype=float)

    # Forward-fill NaN values to propagate last known equity
    combined = combined.fillna(method="ffill")

    # Sum across all columns to get aggregate equity
    result = combined.sum(axis=1)
    return result
