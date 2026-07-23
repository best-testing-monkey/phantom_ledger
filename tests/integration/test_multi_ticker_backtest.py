"""Regression tests for the multi-ticker bar bug in SimulationEngine.

Previously, run_backtest/run_paper/run_paper_tick fetched bars for only
tickers[0] and then evaluated every ticker's pending orders / open positions
/ equity mark-to-market against that ONE shared bar. This meant, e.g., an
order for a $3 ticker could fill at a $300 ticker's price. These tests build
two tickers at clearly different price levels (mirroring the real
AAPL ~$300 vs NG=F ~$3 case that exposed the bug) and assert each ticker's
own bar is used throughout.
"""

from unittest.mock import MagicMock

import pandas as pd

from phantom.models.order import Order


def _mock_provider_for(ticker_frames: dict[str, pd.DataFrame]) -> MagicMock:
    """Build a DataProvider mock whose get_bars() returns the right frame
    per-ticker instead of one fixed return_value shared by every ticker."""

    def get_bars_side_effect(ticker, start, end):
        return ticker_frames.get(ticker, pd.DataFrame())

    mock_provider = MagicMock()
    mock_provider.get_bars.side_effect = get_bars_side_effect
    mock_provider.get_dividends.return_value = []
    return mock_provider


class TestMultiTickerBacktest:
    def test_orders_fill_and_equity_marks_to_each_tickers_own_price(
        self, phantom_instance, degiro_profile
    ):
        """Two tickers, one ~$300 one ~$3, same 3 trading days. Each order
        must fill at ITS OWN ticker's Open, and the equity snapshot's
        market_value/unrealized must use each position's OWN ticker's Close.
        """
        ph = phantom_instance

        from phantom.db.repositories.broker_repo import BrokerRepo

        # Zero-cost broker profile so cash movement from entry costs is
        # exactly notional (fill_price * quantity), keeping the expected
        # equity hand-calculation simple and exact.
        zero_cost_profile = degiro_profile.model_copy(
            update={
                "name": "ZERO_COST_TEST",
                "commission": degiro_profile.commission.model_copy(
                    update={"fixed_fee": 0.0}
                ),
                "spread": degiro_profile.spread.model_copy(
                    update={"fixed_spread_pct": 0.0}
                ),
                "slippage": degiro_profile.slippage.model_copy(
                    update={"fixed_pct": 0.0}
                ),
                "fx_conversion_pct": 0.0,
            }
        )
        broker_repo = BrokerRepo(ph._conn)
        broker_repo.create(zero_cost_profile)

        account = ph.accounts.create(
            name="multi_ticker_test",
            account_type="manual",
            broker=zero_cost_profile.name,
            capital=10000.0,
        )

        dates = pd.bdate_range("2025-01-02", periods=3)

        aapl_bars = pd.DataFrame(
            {
                "Open": [300.0, 300.5, 301.5],
                "High": [301.0, 302.0, 303.0],
                "Low": [299.0, 300.0, 301.0],
                "Close": [300.5, 301.5, 302.5],
                "Volume": [1_000_000] * 3,
            },
            index=dates,
        )
        ngf_bars = pd.DataFrame(
            {
                "Open": [3.0, 3.05, 3.15],
                "High": [3.1, 3.2, 3.3],
                "Low": [2.9, 3.0, 3.1],
                "Close": [3.05, 3.15, 3.25],
                "Volume": [500_000] * 3,
            },
            index=dates,
        )

        aapl_order = Order(
            account_id=account.id,
            ticker="AAPL",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=10,
        )
        ngf_order = Order(
            account_id=account.id,
            ticker="NG=F",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=100,
        )
        ph.orders.place(account_id=account.id, order=aapl_order)
        ph.orders.place(account_id=account.id, order=ngf_order)

        mock_provider = _mock_provider_for({"AAPL": aapl_bars, "NG=F": ngf_bars})

        result = ph.runner.backtest(
            account_id=account.id,
            tickers=["AAPL", "NG=F"],
            start="2025-01-02",
            end="2025-01-08",
            data_provider=mock_provider,
        )

        # --- Fills: each ticker fills at ITS OWN Open, not the other's ---
        assert len(result.filled_orders) == 2
        fills_by_ticker = {o.ticker: o for o in result.filled_orders}
        assert fills_by_ticker["AAPL"].fill_price == 300.0
        assert fills_by_ticker["NG=F"].fill_price == 3.0
        # Sanity: under the old bug, both would have filled at whichever
        # ticker happened to be tickers[0]'s Open (300.0).
        assert fills_by_ticker["NG=F"].fill_price != fills_by_ticker["AAPL"].fill_price

        # --- Equity: last snapshot must mark each position to its OWN
        # ticker's Close on day 3, not tickers[0]'s Close for everything ---
        assert len(result.equity_curve) == 3
        last_point = result.equity_curve[-1]

        expected_market_value = 10 * 302.5 + 100 * 3.25  # = 3025 + 325 = 3350.0
        expected_unrealized = (302.5 - 300.0) * 10 + (3.25 - 3.0) * 100  # = 25 + 25 = 50.0
        expected_cash = 10000.0 - (10 * 300.0) - (100 * 3.0)  # zero-cost entry = 6700.0
        expected_equity = expected_cash + expected_market_value  # = 10050.0

        assert last_point.cash == expected_cash
        assert last_point.unrealized_pnl == expected_unrealized
        assert last_point.equity == expected_equity

        # Under the old bug, market_value/unrealized would have used
        # tickers[0]'s (AAPL's) Close for the NG=F position too, e.g.
        # 100 * 302.5 instead of 100 * 3.25 - wildly different total.
        wrong_market_value_under_old_bug = 10 * 302.5 + 100 * 302.5
        assert last_point.equity != expected_cash + wrong_market_value_under_old_bug

    def test_mismatched_trading_days_carry_forward_and_skip(
        self, phantom_instance, degiro_profile
    ):
        """Ticker A trades all 3 days; ticker B is missing the middle day
        (e.g. a different futures session calendar). The engine must not
        crash, must skip evaluating B's position on the day it has no bar,
        and must carry forward B's last known Close for mark-to-market on
        that day.
        """
        ph = phantom_instance

        from phantom.db.repositories.broker_repo import BrokerRepo

        zero_cost_profile = degiro_profile.model_copy(
            update={
                "name": "ZERO_COST_TEST_2",
                "commission": degiro_profile.commission.model_copy(
                    update={"fixed_fee": 0.0}
                ),
                "spread": degiro_profile.spread.model_copy(
                    update={"fixed_spread_pct": 0.0}
                ),
                "slippage": degiro_profile.slippage.model_copy(
                    update={"fixed_pct": 0.0}
                ),
                "fx_conversion_pct": 0.0,
            }
        )
        broker_repo = BrokerRepo(ph._conn)
        broker_repo.create(zero_cost_profile)

        account = ph.accounts.create(
            name="mismatched_days_test",
            account_type="manual",
            broker=zero_cost_profile.name,
            capital=10000.0,
        )

        dates = pd.bdate_range("2025-01-02", periods=3)  # d1, d2, d3

        a_bars = pd.DataFrame(
            {
                "Open": [300.0, 300.5, 301.5],
                "High": [301.0, 302.0, 303.0],
                "Low": [299.0, 300.0, 301.0],
                "Close": [300.5, 301.5, 302.5],
                "Volume": [1_000_000] * 3,
            },
            index=dates,
        )
        # B only has bars for d1 and d3 - d2 is missing entirely.
        b_dates = dates[[0, 2]]
        b_bars = pd.DataFrame(
            {
                "Open": [3.0, 3.05],
                "High": [3.1, 3.3],
                "Low": [2.9, 3.0],
                "Close": [3.05, 3.15],
                "Volume": [500_000] * 2,
            },
            index=b_dates,
        )

        a_order = Order(
            account_id=account.id,
            ticker="A",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=10,
        )
        b_order = Order(
            account_id=account.id,
            ticker="B",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=50,
        )
        ph.orders.place(account_id=account.id, order=a_order)
        ph.orders.place(account_id=account.id, order=b_order)

        mock_provider = _mock_provider_for({"A": a_bars, "B": b_bars})

        # Should not raise despite B missing a trading day in the middle.
        result = ph.runner.backtest(
            account_id=account.id,
            tickers=["A", "B"],
            start="2025-01-02",
            end="2025-01-08",
            data_provider=mock_provider,
        )

        assert len(result.equity_curve) == 3  # master index = union = 3 days
        assert len(result.filled_orders) == 2
        fills_by_ticker = {o.ticker: o for o in result.filled_orders}
        assert fills_by_ticker["A"].fill_price == 300.0
        assert fills_by_ticker["B"].fill_price == 3.0

        d1_point, d2_point, d3_point = result.equity_curve

        # d2: B has no bar. market_value must carry forward B's d1 Close
        # (3.05) rather than crashing or dropping the B position's value.
        expected_market_value_d2 = 10 * 301.5 + 50 * 3.05  # = 3015 + 152.5 = 3167.5
        expected_unrealized_d2 = (301.5 - 300.0) * 10 + (3.05 - 3.0) * 50  # = 15 + 2.5 = 17.5
        expected_cash = 10000.0 - (10 * 300.0) - (50 * 3.0)  # = 6850.0
        assert d2_point.cash == expected_cash
        assert d2_point.unrealized_pnl == expected_unrealized_d2
        assert d2_point.equity == expected_cash + expected_market_value_d2

        # d3: B has a bar again, Close updates to 3.15.
        expected_market_value_d3 = 10 * 302.5 + 50 * 3.15  # = 3025 + 157.5 = 3182.5
        expected_unrealized_d3 = (302.5 - 300.0) * 10 + (3.15 - 3.0) * 50  # = 25 + 7.5 = 32.5
        assert d3_point.unrealized_pnl == expected_unrealized_d3
        assert d3_point.equity == expected_cash + expected_market_value_d3
