"""Output formatters for reports and metrics."""

import logging

from phantom.reports.metrics import EquityPoint

logger = logging.getLogger(__name__)


def render_equity_chart(curve: list[EquityPoint], account_name: str) -> None:
    """Render an equity curve as a terminal chart.

    Args:
        curve: List of EquityPoint data
        account_name: Name of the account for title

    Requires plotext to be installed: uv add plotext[charts]
    """
    try:
        import plotext as plt
    except ImportError:
        print("Install plotext for terminal charts: uv add plotext")
        return

    if len(curve) < 2:
        print("Not enough data to render chart (minimum 2 points).")
        return

    try:
        dates = [pt.timestamp.strftime("%Y-%m-%d") for pt in curve]
        equities = [pt.equity for pt in curve]

        plt.clear_figure()
        plt.theme("dark")
        plt.plot_size(80, 24)
        plt.title(f"Equity Curve — {account_name}")
        plt.xlabel("Date")
        plt.ylabel("Equity")
        plt.plot(dates, equities)
        plt.show()
    except Exception as e:
        logger.error("Failed to render chart: %s", e)
        print(f"Failed to render chart: {e}")
