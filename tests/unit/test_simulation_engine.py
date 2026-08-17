"""Tests for E17-S02: a single order's fill failure must not abort the
whole batch. Previously, InsufficientFundsError raised inside
handle_fill() propagated straight out of run_backtest()'s fill loop,
aborting processing for every other order that step.
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


class TestFillBatchPartialFailure:
    def test_second_of_three_orders_unfunded_does_not_abort_batch(
        self, phantom_instance, degiro_profile
    ):
        """3 market orders for 3 tickers evaluate/fill on the same step.
        Order 2 is sized so its cost alone exceeds what's left of cash
        after order 1 fills; order 2 being rejected must not consume any
        cash, so order 3 (which fits in what's left after order 1) still
        fills. No exception should propagate out of run_backtest().
        """
        ph = phantom_instance

        from phantom.db.repositories.broker_repo import BrokerRepo

        # Zero-cost broker profile so cash movement is exactly notional
        # (fill_price * quantity), keeping the funding math exact.
        zero_cost_profile = degiro_profile.model_copy(
            update={
                "name": "ZERO_COST_FILL_BATCH_TEST",
                "commission": degiro_profile.commission.model_copy(update={"fixed_fee": 0.0}),
                "spread": degiro_profile.spread.model_copy(update={"fixed_spread_pct": 0.0}),
                "slippage": degiro_profile.slippage.model_copy(update={"fixed_pct": 0.0}),
                "fx_conversion_pct": 0.0,
            }
        )
        broker_repo = BrokerRepo(ph._conn)
        broker_repo.create(zero_cost_profile)

        account = ph.accounts.create(
            name="fill_batch_test",
            account_type="manual",
            broker=zero_cost_profile.name,
            capital=10000.0,
        )

        dates = pd.bdate_range("2025-01-02", periods=1)

        def make_bars(open_price: float) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Open": [open_price],
                    "High": [open_price + 1.0],
                    "Low": [open_price - 1.0],
                    "Close": [open_price],
                    "Volume": [1_000_000],
                },
                index=dates,
            )

        # Order 1: 10 * 300 = 3000 notional -> cash after fill = 7000.
        # Order 2: 100 * 100 = 10000 notional -> exceeds the 7000 left,
        #          must be rejected (and must NOT consume cash).
        # Order 3: 10 * 50 = 500 notional -> comfortably fits in the 7000
        #          still available after order 1 (order 2's rejection did
        #          not touch cash), so it must still fill.
        t1_bars = make_bars(300.0)
        t2_bars = make_bars(100.0)
        t3_bars = make_bars(50.0)

        order1 = Order(
            account_id=account.id,
            ticker="T1",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=10,
        )
        order2 = Order(
            account_id=account.id,
            ticker="T2",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=100,
        )
        order3 = Order(
            account_id=account.id,
            ticker="T3",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=10,
        )
        ph.orders.place(account_id=account.id, order=order1)
        ph.orders.place(account_id=account.id, order=order2)
        ph.orders.place(account_id=account.id, order=order3)

        mock_provider = _mock_provider_for({"T1": t1_bars, "T2": t2_bars, "T3": t3_bars})

        # Must not raise despite order 2 being unfundable.
        result = ph.runner.backtest(
            account_id=account.id,
            tickers=["T1", "T2", "T3"],
            start="2025-01-02",
            end="2025-01-08",
            data_provider=mock_provider,
        )

        assert len(result.filled_orders) == 2
        filled_tickers = {o.ticker for o in result.filled_orders}
        assert filled_tickers == {"T1", "T3"}

        assert len(result.rejected_orders) == 1
        assert result.rejected_orders[0].ticker == "T2"
        assert result.rejected_orders[0].status == "rejected"
        assert result.rejected_orders[0].rejection_reason == "insufficient_funds"

        # Order 3 filled at 50 * 10 = 500, so final cash reflects only
        # order 1 (3000) and order 3 (500) leaving the account - order 2's
        # rejection must not have deducted anything.
        expected_cash = 10000.0 - (10 * 300.0) - (10 * 50.0)
        assert result.account.cash == expected_cash
