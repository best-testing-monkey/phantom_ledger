from datetime import datetime, timezone

import pytest

from phantom.errors import ValidationError
from phantom.reports.metrics import (
    EquityPoint,
    aggregate_costs,
    calculate_metrics,
    calculate_trade_metrics,
)


class TestCalculateMetrics:
    def test_flat_curve_zero_drawdown(self):
        curve = [
            EquityPoint(datetime(2025, 1, 1, tzinfo=timezone.utc), 10000.0),
            EquityPoint(datetime(2025, 6, 1, tzinfo=timezone.utc), 10000.0),
        ]
        metrics = calculate_metrics(curve)
        assert metrics.total_return_pct == pytest.approx(0.0)
        assert metrics.max_drawdown_pct == pytest.approx(0.0)

    def test_monotone_decline(self):
        curve = [
            EquityPoint(datetime(2025, 1, 1, tzinfo=timezone.utc), 10000.0),
            EquityPoint(datetime(2025, 6, 1, tzinfo=timezone.utc), 8000.0),
        ]
        metrics = calculate_metrics(curve)
        assert metrics.total_return_pct == pytest.approx(-20.0)
        assert metrics.max_drawdown_pct == pytest.approx(20.0)

    def test_raises_on_short_curve(self):
        with pytest.raises(ValidationError):
            calculate_metrics([EquityPoint(datetime(2025, 1, 1, tzinfo=timezone.utc), 10000.0)])

    def test_wipeout_curve_gives_real_cagr_not_complex(self):
        # A leveraged/margin account can end at or below zero equity, not
        # just approach it. (final / initial) is then <= 0, and a naive
        # fractional power there returns a Python complex number, which
        # crashes EquityMetrics' float validation (see calculate_metrics'
        # comment). -100% CAGR is the correct value for a total wipeout.
        curve = [
            EquityPoint(datetime(2025, 1, 1, tzinfo=timezone.utc), 10000.0),
            EquityPoint(datetime(2025, 7, 1, tzinfo=timezone.utc), 0.0),
        ]
        metrics = calculate_metrics(curve)
        assert metrics.cagr_pct == pytest.approx(-100.0)
        assert isinstance(metrics.cagr_pct, float)

    def test_negative_equity_curve_gives_real_cagr_not_complex(self):
        curve = [
            EquityPoint(datetime(2025, 1, 1, tzinfo=timezone.utc), 10000.0),
            EquityPoint(datetime(2025, 7, 1, tzinfo=timezone.utc), -50.0),
        ]
        metrics = calculate_metrics(curve)
        assert metrics.cagr_pct == pytest.approx(-100.0)
        assert isinstance(metrics.cagr_pct, float)

    def test_known_sequence(self):
        curve = [
            EquityPoint(datetime(2025, 1, 1, tzinfo=timezone.utc), 10000.0),
            EquityPoint(datetime(2025, 1, 2, tzinfo=timezone.utc), 11000.0),
            EquityPoint(datetime(2025, 1, 3, tzinfo=timezone.utc), 9000.0),
            EquityPoint(datetime(2025, 1, 4, tzinfo=timezone.utc), 12000.0),
        ]
        metrics = calculate_metrics(curve)
        # Max drawdown: peak=11000, trough=9000, dd = (11000-9000)/11000*100 ≈ 18.18%
        assert metrics.max_drawdown_pct == pytest.approx(100 * 2000 / 11000)
        assert metrics.total_return_pct == pytest.approx(20.0)


class TestTradeMetrics:
    def _make_closed_position(self, realized_pnl):
        from phantom.models.position import Position
        from phantom.utils.datetime import now_utc

        return Position(
            account_id="acc1",
            ticker="AAPL",
            instrument_type="stock",
            direction="long",
            entry_order_id="ord1",
            entry_price=100.0,
            entry_datetime=now_utc(),
            quantity=10.0,
            notional=1000.0,
            status="closed",
            exit_price=100.0 + realized_pnl / 10.0,
            realized_pnl=realized_pnl,
        )

    def test_win_rate(self):
        positions = [
            self._make_closed_position(100.0),
            self._make_closed_position(-50.0),
            self._make_closed_position(200.0),
        ]
        metrics = calculate_trade_metrics(positions)
        assert metrics.trade_count == 3
        assert metrics.win_count == 2
        assert metrics.win_rate_pct == pytest.approx(200 / 3)

    def test_all_wins_infinite_profit_factor(self):
        positions = [
            self._make_closed_position(100.0),
            self._make_closed_position(200.0),
        ]
        metrics = calculate_trade_metrics(positions)
        assert metrics.profit_factor == float("inf")

    def test_no_closed_raises(self):
        from phantom.models.position import Position
        from phantom.utils.datetime import now_utc

        open_pos = Position(
            account_id="acc1",
            ticker="AAPL",
            instrument_type="stock",
            direction="long",
            entry_order_id="ord1",
            entry_price=100.0,
            entry_datetime=now_utc(),
            quantity=10.0,
            notional=1000.0,
        )
        with pytest.raises(ValidationError):
            calculate_trade_metrics([open_pos])


class TestAggregateCosts:
    def test_empty_returns_zeros(self):
        summary = aggregate_costs([])
        assert summary.total_cost == 0.0
        assert summary.total_commission == 0.0

    def test_sums_correctly(self):
        from phantom.models.position import Position
        from phantom.utils.datetime import now_utc

        pos = Position(
            account_id="acc1",
            ticker="AAPL",
            instrument_type="stock",
            direction="long",
            entry_order_id="ord1",
            entry_price=100.0,
            entry_datetime=now_utc(),
            quantity=10.0,
            notional=1000.0,
            commission_entry=1.0,
            commission_exit=1.0,
            spread_cost=0.5,
            slippage_cost=0.3,
            overnight_costs=0.0,
            fx_conversion_cost=2.0,
        )
        summary = aggregate_costs([pos])
        assert summary.total_commission == pytest.approx(2.0)
        assert summary.total_spread == pytest.approx(0.5)
        assert summary.total_cost == pytest.approx(2.0 + 0.5 + 0.3 + 2.0)
