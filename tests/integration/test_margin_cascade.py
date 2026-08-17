"""Integration test for margin stop-out cascade."""

from phantom.engine.margin_engine import MarginEngine
from phantom.models.account import Account
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
from phantom.models.position import Position
from phantom.utils.datetime import now_utc


def _cfd_position(margin_required: float) -> Position:
    return Position(
        account_id="test-account-1",
        ticker="TEST",
        instrument_type="cfd",
        direction="long",
        entry_order_id="order-1",
        entry_price=100.0,
        entry_datetime=now_utc(),
        quantity=1.0,
        notional=100.0,
        margin_required=margin_required,
    )


class TestMarginCascade:
    """Integration tests for margin stop-out cascade."""

    def test_cascade_recovers_when_margin_improves(self):
        """Test cascade stops when margin level recovers above stop_out_level."""
        broker_profile = BrokerProfile(
            name="CFD_TEST",
            commission=CommissionModel(model_type="fixed", fixed_fee=0.0),
            spread=SpreadModel(model_type="fixed", fixed_spread_pct=0.0),
            slippage=SlippageModel(model_type="fixed_pct", fixed_pct=0.0),
            overnight=OvernightModel(
                long_markup_pct=0.0,
                short_markup_pct=0.0,
                day_divisor=365,
                rate_source="manual",
                manual_rate=0.0,
            ),
            margin=MarginModel(
                default_margin_pct=0.02,  # 2% default margin
                margin_call_level=150.0,  # 150%
                stop_out_level=50.0,  # 50%
            ),
            dividend=DividendModel(
                withholding_rates={"US": 0.0},
                cfd_dividend_adjustment=1.0,
                cfd_short_dividend_charge=1.0,
            ),
            fx_conversion_pct=0.0,
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

        account = Account(
            id="test-account-cascade",
            name="Cascade Test Account",
            account_type="manual",
            broker_profile_id="test-broker-cascade",
            base_currency="EUR",
            initial_capital=10000.0,
            cash=2000.0,  # 40% margin level - in stop-out
        )

        margin_engine = MarginEngine()

        # Test initial stop-out
        # used_margin = sum(margin_required) = 200000 * 0.02 = 4000
        # level = (2000 / 4000) * 100 = 50% (at the boundary)
        status = margin_engine.check(
            account,
            broker_profile,
            [_cfd_position(200000.0 * broker_profile.margin.default_margin_pct)],
        )
        assert status.status == "stop_out"
        assert status.level == 50.0

        # If we reduce open position market value (e.g., via closure),
        # margin level should improve
        reduced_market_value = 100000.0  # Half of original
        status = margin_engine.check(
            account,
            broker_profile,
            [_cfd_position(reduced_market_value * broker_profile.margin.default_margin_pct)],
        )

        # level = (2000 / (100000 * 0.02)) * 100 = (2000 / 2000) * 100 = 100%
        # Should now be 'margin_call' (between 50 and 150%)
        assert status.status == "margin_call"
        assert status.level == 100.0

    def test_margin_status_transitions(self):
        """Test all margin status transitions."""
        broker_profile = BrokerProfile(
            name="CFD_TRANSITIONS",
            commission=CommissionModel(model_type="fixed", fixed_fee=0.0),
            spread=SpreadModel(model_type="fixed", fixed_spread_pct=0.0),
            slippage=SlippageModel(model_type="fixed_pct", fixed_pct=0.0),
            overnight=OvernightModel(
                long_markup_pct=0.0,
                short_markup_pct=0.0,
                day_divisor=365,
                rate_source="manual",
                manual_rate=0.0,
            ),
            margin=MarginModel(
                default_margin_pct=0.05,  # 5% default margin
                margin_call_level=100.0,  # 100%
                stop_out_level=50.0,  # 50%
            ),
            dividend=DividendModel(
                withholding_rates={"US": 0.0},
                cfd_dividend_adjustment=1.0,
                cfd_short_dividend_charge=1.0,
            ),
            fx_conversion_pct=0.0,
            fx_base_currency="EUR",
            min_order_size=0.01,
            max_leverage=20.0,
            trading_hours=TradingHoursConfig(
                timezone="UTC",
                open="00:00",
                close="23:59",
                pre_market=False,
                post_market=False,
            ),
            supported_instruments=["cfd", "stock"],
        )

        account = Account(
            id="test-transitions",
            name="Transitions Test",
            account_type="manual",
            broker_profile_id="test-broker-transitions",
            base_currency="EUR",
            initial_capital=10000.0,
            cash=10000.0,
        )

        margin_engine = MarginEngine()

        # Test 1: OK status with 20000 market value
        # used_margin = sum(margin_required) = 20000 * 0.05 = 1000
        # level = (10000 / 1000) * 100 = 1000%
        status = margin_engine.check(
            account,
            broker_profile,
            [_cfd_position(20000.0 * broker_profile.margin.default_margin_pct)],
        )
        assert status.status == "ok"
        assert status.level == 1000.0

        # Test 2: Margin call with 200000 market value
        # used_margin = sum(margin_required) = 200000 * 0.05 = 10000
        # level = (10000 / 10000) * 100 = 100%
        status = margin_engine.check(
            account,
            broker_profile,
            [_cfd_position(200000.0 * broker_profile.margin.default_margin_pct)],
        )
        assert status.status == "margin_call"
        assert status.level == 100.0

        # Test 3: Stop-out with 400000 market value
        # used_margin = sum(margin_required) = 400000 * 0.05 = 20000
        # level = (10000 / 20000) * 100 = 50%
        status = margin_engine.check(
            account,
            broker_profile,
            [_cfd_position(400000.0 * broker_profile.margin.default_margin_pct)],
        )
        assert status.status == "stop_out"
        assert status.level == 50.0

        # Test 4: Below stop-out with 500000 market value
        # used_margin = sum(margin_required) = 500000 * 0.05 = 25000
        # level = (10000 / 25000) * 100 = 40%
        status = margin_engine.check(
            account,
            broker_profile,
            [_cfd_position(500000.0 * broker_profile.margin.default_margin_pct)],
        )
        assert status.status == "stop_out"
        assert status.level == 40.0
