from unittest.mock import MagicMock

import pandas as pd

from phantom.models.order import Order


class TestBacktest:
    def test_market_order_fills_and_tp_triggers(self, phantom_instance, degiro_profile):
        """Market buy at open, TP at 195.0, SL at 180.0. Price hits TP on bar 3."""
        ph = phantom_instance

        from phantom.db.repositories.broker_repo import BrokerRepo

        broker_repo = BrokerRepo(ph._conn)
        broker_repo.create(degiro_profile)

        account = ph.accounts.create(
            name="bt_test",
            account_type="manual",
            broker=degiro_profile.name,
            capital=10000.0,
        )

        dates = pd.bdate_range("2025-01-02", periods=5, freq="B")
        prices = pd.DataFrame(
            {
                "Open": [185.0, 186.0, 188.0, 190.0, 191.0],
                "High": [186.0, 187.0, 189.0, 196.0, 192.0],
                "Low": [184.0, 185.0, 187.0, 189.0, 190.0],
                "Close": [185.5, 186.5, 188.5, 195.5, 191.5],
                "Volume": [1_000_000] * 5,
            },
            index=dates,
        )

        order = Order(
            account_id=account.id,
            ticker="AAPL",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=10,
            take_profit=195.0,
            stop_loss=180.0,
        )
        ph.orders.place(account_id=account.id, order=order)

        mock_provider = MagicMock()
        mock_provider.get_bars.return_value = prices

        result = ph.runner.backtest(
            account_id=account.id,
            tickers=["AAPL"],
            start="2025-01-02",
            end="2025-01-08",
            data_provider=mock_provider,
        )

        assert len(result.filled_orders) == 1
        assert result.filled_orders[0].fill_price == 185.0

        assert len(result.closed_positions) == 1
        pos = result.closed_positions[0]
        assert pos.exit_price == 195.0
        assert pos.close_reason == "tp"

        assert len(result.equity_curve) == 5
