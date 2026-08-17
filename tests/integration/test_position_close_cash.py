"""Integration tests for E17-S06: PositionAPI.close()'s direction/instrument-
type-aware cash update.

These exercise the public API only (ph.orders.place/fill_manual,
ph.positions.close) per CLAUDE.md's integration-test rules, and each test
independently computes its own expected cash/realized_pnl value from the
broker profile's cost model rather than reusing production code.
"""

import pytest

from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.models.broker import (
    BrokerProfile,
    CommissionModel,
    DividendModel,
    MarginModel,
    OvernightModel,
    SlippageModel,
    SpreadModel,
    TradingHoursConfig,
)
from phantom.models.order import Order


def _cfd_profile(name: str) -> BrokerProfile:
    """Broker profile supporting CFDs with simple, hand-computable costs."""
    return BrokerProfile(
        name=name,
        commission=CommissionModel(model_type="fixed", fixed_fee=2.0),
        spread=SpreadModel(model_type="fixed", fixed_spread_pct=0.001),
        slippage=SlippageModel(model_type="fixed_pct", fixed_pct=0.0005),
        overnight=OvernightModel(
            long_markup_pct=0.0,
            short_markup_pct=0.0,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.0,
        ),
        margin=MarginModel(
            default_margin_pct=0.1,
            margin_call_level=100.0,
            stop_out_level=50.0,
        ),
        dividend=DividendModel(
            withholding_rates={"US": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        ),
        fx_conversion_pct=0.01,
        fx_base_currency="EUR",
        min_order_size=0.01,
        max_leverage=50.0,
        trading_hours=TradingHoursConfig(
            timezone="UTC",
            open="00:00",
            close="23:59",
            pre_market=False,
            post_market=False,
        ),
        supported_instruments=["cfd", "stock"],
    )


def _cfd_profile_per_share(name: str) -> BrokerProfile:
    """Broker profile with per-share commission, for the partial-close test
    (per-share scales with quantity, unlike a fixed fee, so entry- and
    exit-slice commissions differ as expected for a partial close)."""
    return BrokerProfile(
        name=name,
        commission=CommissionModel(model_type="per_share", per_share=0.01),
        spread=SpreadModel(model_type="fixed", fixed_spread_pct=0.0004),
        slippage=SlippageModel(model_type="fixed_pct", fixed_pct=0.0004),
        overnight=OvernightModel(
            long_markup_pct=0.0,
            short_markup_pct=0.0,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.0,
        ),
        margin=MarginModel(
            default_margin_pct=0.1,
            margin_call_level=100.0,
            stop_out_level=50.0,
        ),
        dividend=DividendModel(
            withholding_rates={"US": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        ),
        fx_conversion_pct=0.0006,
        fx_base_currency="EUR",
        min_order_size=0.01,
        max_leverage=50.0,
        trading_hours=TradingHoursConfig(
            timezone="UTC",
            open="00:00",
            close="23:59",
            pre_market=False,
            post_market=False,
        ),
        supported_instruments=["cfd", "stock"],
    )


class TestPositionCloseCash:
    def test_full_close_short_cfd_matches_direction_aware_formula(self, phantom_instance):
        """A profitable short CFD closed via ph.positions.close() must return
        margin_required + gross_pnl - exit_costs.total, not the old
        direction-blind exit_price * quantity - costs.total (which would be
        visibly wrong for a short: price fell, so exit_price*quantity is
        SMALLER than entry notional, understating the actual profit)."""
        ph = phantom_instance
        profile = _cfd_profile("CFD_SHORT_TEST")
        BrokerRepo(ph._conn).create(profile)

        account = ph.accounts.create(
            name="short_cfd_acct",
            account_type="manual",
            broker=profile.name,
            capital=10000.0,
            currency="EUR",
        )

        order = Order(
            account_id=account.id,
            ticker="XYZ",
            instrument_type="cfd",
            direction="short",
            order_type="market",
            quantity=10,
        )
        placed = ph.orders.place(account_id=account.id, order=order)
        _, position = ph.orders.fill_manual(placed.id, fill_price=100.0)

        # Entry costs (fx_required=True since account currency EUR != USD):
        # commission=2.0 (fixed), spread=0.001*100*10=1.0,
        # slippage=0.0005*100*10=0.5, fx=0.01*100*10=10.0
        entry_costs_total = 2.0 + 1.0 + 0.5 + 10.0
        margin_required = 10.0 * 100.0 * 0.1  # notional * margin_pct = 100.0
        assert position.margin_required == pytest.approx(margin_required)

        cash_after_entry = ph.accounts.get(account.id).cash
        assert cash_after_entry == pytest.approx(10000.0 - (margin_required + entry_costs_total))

        # Close profitably: price fell from 100 to 90 (good for a short).
        exit_price = 90.0
        closed = ph.positions.close(position.id, close_reason="manual", exit_price=exit_price)

        # Exit costs, computed independently (fx_required defaults False on exit):
        # commission=2.0, spread=0.001*90*10=0.9, slippage=0.0005*90*10=0.45
        exit_costs_total = 2.0 + 0.9 + 0.45
        gross_pnl = (100.0 - exit_price) * 10  # short: entry - exit, per unit
        expected_cash_delta = margin_required + gross_pnl - exit_costs_total

        account_after = ph.accounts.get(account.id)
        assert account_after.cash == pytest.approx(cash_after_entry + expected_cash_delta)

        # Sanity: this must differ from the OLD, direction-blind formula
        # (exit_price * quantity - exit_costs_total), proving the fix changed
        # behavior for shorts.
        old_buggy_delta = exit_price * 10 - exit_costs_total
        assert expected_cash_delta != pytest.approx(old_buggy_delta)

        assert closed.status == "closed"
        assert closed.exit_price == exit_price

    def test_full_close_long_stock_unchanged(self, phantom_instance, degiro_profile):
        """A long stock position closed via ph.positions.close() must still
        use the already-correct notional-based formula (no regression)."""
        ph = phantom_instance
        BrokerRepo(ph._conn).create(degiro_profile)

        account = ph.accounts.create(
            name="long_stock_acct",
            account_type="manual",
            broker=degiro_profile.name,
            capital=10000.0,
            currency="EUR",
        )

        order = Order(
            account_id=account.id,
            ticker="AAPL",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=10,
        )
        placed = ph.orders.place(account_id=account.id, order=order)
        _, position = ph.orders.fill_manual(placed.id, fill_price=100.0)

        # Entry costs (fx_required=True, EUR account): commission=1.0 (fixed),
        # spread=0.0005*100*10=0.5, slippage=0.0003*100*10=0.3,
        # fx=0.0025*100*10=2.5
        entry_costs_total = 1.0 + 0.5 + 0.3 + 2.5
        notional = 100.0 * 10
        cash_after_entry = ph.accounts.get(account.id).cash
        assert cash_after_entry == pytest.approx(10000.0 - (notional + entry_costs_total))

        exit_price = 110.0
        closed = ph.positions.close(position.id, close_reason="manual", exit_price=exit_price)

        # Exit costs (fx_required defaults False): commission=1.0,
        # spread=0.0005*110*10=0.55, slippage=0.0003*110*10=0.33
        exit_costs_total = 1.0 + 0.55 + 0.33
        expected_cash_delta = exit_price * 10 - exit_costs_total

        account_after = ph.accounts.get(account.id)
        assert account_after.cash == pytest.approx(cash_after_entry + expected_cash_delta)
        assert closed.status == "closed"

    def test_partial_close_cfd_proportional_formulas(self, phantom_instance):
        """Partial close of a long CFD position: both realized_pnl and cash
        must use the proportional (fraction-scaled) formulas, matching the
        ticket's derived formulas exactly."""
        ph = phantom_instance
        profile = _cfd_profile_per_share("CFD_PARTIAL_TEST")
        BrokerRepo(ph._conn).create(profile)

        account = ph.accounts.create(
            name="partial_cfd_acct",
            account_type="manual",
            broker=profile.name,
            capital=20000.0,
            currency="EUR",
        )

        order = Order(
            account_id=account.id,
            ticker="XAUUSD",
            instrument_type="cfd",
            direction="long",
            order_type="market",
            quantity=100,
        )
        placed = ph.orders.place(account_id=account.id, order=order)
        _, position = ph.orders.fill_manual(placed.id, fill_price=100.0)

        # Entry costs (fx_required=True): commission=100*0.01=1.0,
        # spread=0.0004*100*100=4.0, slippage=0.0004*100*100=4.0,
        # fx=0.0006*100*100=6.0 -> total = 15.0
        entry_commission = 100 * 0.01
        entry_spread = 0.0004 * 100.0 * 100
        entry_slippage = 0.0004 * 100.0 * 100
        entry_fx = 0.0006 * 100.0 * 100
        entry_costs_total = entry_commission + entry_spread + entry_slippage + entry_fx
        assert entry_costs_total == pytest.approx(15.0)

        margin_required = 100.0 * 100.0 * 0.1  # notional * margin_pct = 1000.0
        assert position.margin_required == pytest.approx(margin_required)

        cash_after_entry = ph.accounts.get(account.id).cash
        assert cash_after_entry == pytest.approx(20000.0 - (margin_required + entry_costs_total))

        # Partial close 40 of 100 units at exit_price=110.
        quantity = 40
        exit_price = 110.0
        updated_position = ph.positions.close(
            position.id, close_reason="manual", exit_price=exit_price, quantity=quantity
        )

        # Exit costs for the 40-unit slice (fx_required defaults False):
        exit_commission = quantity * 0.01
        exit_spread = 0.0004 * exit_price * quantity
        exit_slippage = 0.0004 * exit_price * quantity
        exit_costs_total = exit_commission + exit_spread + exit_slippage
        assert exit_costs_total == pytest.approx(3.92)

        fraction = quantity / 100.0
        proportional_entry_costs = entry_costs_total * fraction
        assert proportional_entry_costs == pytest.approx(6.0)

        gross_pnl = (exit_price - 100.0) * quantity
        assert gross_pnl == pytest.approx(400.0)

        expected_realized_pnl = gross_pnl - proportional_entry_costs - exit_costs_total
        assert expected_realized_pnl == pytest.approx(390.08)
        assert updated_position.realized_pnl == pytest.approx(expected_realized_pnl)
        assert updated_position.quantity == 60

        released_margin = margin_required * fraction
        assert released_margin == pytest.approx(400.0)
        expected_cash_delta = released_margin + gross_pnl - exit_costs_total
        assert expected_cash_delta == pytest.approx(796.08)

        account_after = ph.accounts.get(account.id)
        assert account_after.cash == pytest.approx(cash_after_entry + expected_cash_delta)
