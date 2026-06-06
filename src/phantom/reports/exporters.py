from __future__ import annotations

import csv
from pathlib import Path

from phantom.reports.metrics import EquityPoint


def export_equity_csv(curve: list[EquityPoint], path: str | Path) -> int:
    """Export equity curve to CSV file.

    Args:
        curve: List of EquityPoint objects
        path: File path to write to

    Returns:
        Number of rows written
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "equity", "drawdown_pct"])

        peak = curve[0].equity if curve else 0.0
        for pt in curve:
            if pt.equity > peak:
                peak = pt.equity
            drawdown = (peak - pt.equity) / peak * 100 if peak > 0 else 0.0
            writer.writerow([pt.timestamp.isoformat(), f"{pt.equity:.2f}", f"{drawdown:.2f}"])

    return len(curve)
