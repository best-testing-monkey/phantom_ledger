"""Integration tests for E17-S07: BrokerAPI.update() preserving FK relationships.

This test verifies that updating a broker profile's config (e.g. changing
margin classes) preserves its database ID and all account FK references,
allowing new fills to see the updated config without orphaning the
account's broker_profile_id.
"""

import pytest

from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.models.broker import (
    BrokerProfile,
    CommissionModel,
    DividendModel,
    MarginClassRule,
    MarginModel,
    OvernightModel,
    SlippageModel,
    SpreadModel,
    TradingHoursConfig,
)
from phantom.models.order import Order


def _cfd_profile_with_classes(name: str, classes: list[MarginClassRule]) -> BrokerProfile:
    """Broker profile supporting CFDs with configurable margin classes."""
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
            classes=classes,
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


class TestBrokerProfileUpdate:
    def test_update_margin_classes_affects_new_fills(self, phantom_instance):
        """Update a profile's margin classes and verify new fills use the
        updated rates, demonstrating that the FK is not orphaned and that
        the account can resolve the broker after the update."""
        ph = phantom_instance

        # Create initial profile with NO class for GOLD
        initial_classes = []
        profile = _cfd_profile_with_classes("CFD_UPDATE_TEST", initial_classes)
        BrokerRepo(ph._conn).create(profile)

        # Create an account
        account = ph.accounts.create(
            name="update_test_acct",
            account_type="manual",
            broker=profile.name,
            capital=50000.0,
            currency="EUR",
        )
        initial_broker_profile_id = account.broker_profile_id

        # First fill: GOLD falls back to default_margin_pct=0.1
        order1 = Order(
            account_id=account.id,
            ticker="GOLD",
            instrument_type="cfd",
            direction="long",
            order_type="market",
            quantity=10,
        )
        placed1 = ph.orders.place(account_id=account.id, order=order1)
        _, position1 = ph.orders.fill_manual(placed1.id, fill_price=100.0)

        # Verify first fill uses default_margin_pct=0.1
        margin_required_before = 10 * 100.0 * 0.1  # 100.0
        assert position1.margin_required == pytest.approx(margin_required_before)

        # Now update the profile to ADD a class for GOLD with margin_pct=0.05
        updated_profile = profile.model_copy(
            update={
                "margin": MarginModel(
                    default_margin_pct=0.1,
                    margin_call_level=100.0,
                    stop_out_level=50.0,
                    classes=[
                        MarginClassRule(
                            label="precious_metals",
                            symbols=["GOLD"],
                            margin_pct=0.05,
                        )
                    ],
                )
            }
        )
        ph.brokers.update(profile.name, updated_profile)

        # Verify the profile was updated
        retrieved_profile = ph.brokers.get(profile.name)
        assert len(retrieved_profile.margin.classes) == 1
        assert retrieved_profile.margin.classes[0].label == "precious_metals"
        assert retrieved_profile.margin.classes[0].margin_pct == 0.05

        # Re-fetch account and confirm FK is still valid (not orphaned)
        account_after_update = ph.accounts.get(account.id)
        assert account_after_update.broker_profile_id == initial_broker_profile_id

        # Second fill: GOLD now uses the updated class with margin_pct=0.05
        order2 = Order(
            account_id=account.id,
            ticker="GOLD",
            instrument_type="cfd",
            direction="long",
            order_type="market",
            quantity=10,
        )
        placed2 = ph.orders.place(account_id=account.id, order=order2)
        _, position2 = ph.orders.fill_manual(placed2.id, fill_price=100.0)

        # Verify second fill uses the updated margin_pct=0.05
        margin_required_after = 10 * 100.0 * 0.05  # 50.0
        assert position2.margin_required == pytest.approx(margin_required_after)

        # Sanity check: the two fills should have different margin_required
        assert position1.margin_required != pytest.approx(position2.margin_required)
        assert position2.margin_required == pytest.approx(50.0)
