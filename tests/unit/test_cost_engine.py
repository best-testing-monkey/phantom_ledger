import pytest

from phantom.costs import CostEngine
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


@pytest.fixture
def profile():
    return BrokerProfile(
        name="TEST",
        commission=CommissionModel(model_type="fixed", fixed_fee=1.0),
        spread=SpreadModel(model_type="fixed", fixed_spread_pct=0.0005),
        slippage=SlippageModel(model_type="fixed_pct", fixed_pct=0.0003),
        overnight=OvernightModel(
            long_markup_pct=0.0,
            short_markup_pct=0.0,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.0,
        ),
        margin=MarginModel(
            default_margin_pct=1.0,
            margin_call_level=1.0,
            stop_out_level=0.5,
        ),
        dividend=DividendModel(
            withholding_rates={"US": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        ),
        fx_conversion_pct=0.0025,
        fx_base_currency="EUR",
        min_order_size=1.0,
        max_leverage=1.0,
        trading_hours=TradingHoursConfig(
            timezone="America/New_York",
            open="09:30",
            close="16:00",
            pre_market=False,
            post_market=False,
        ),
        supported_instruments=["stock"],
    )


class TestCostEngine:
    def test_total_equals_sum_of_components(self, profile):
        engine = CostEngine(profile)
        breakdown = engine.entry_costs(
            price=100.0,
            quantity=10,
            ticker="AAPL",
            instrument_type="stock",
        )
        assert breakdown.total == pytest.approx(
            breakdown.commission + breakdown.spread + breakdown.slippage + breakdown.fx
        )

    def test_fx_zero_when_not_required(self, profile):
        engine = CostEngine(profile)
        breakdown = engine.entry_costs(
            price=100.0,
            quantity=10,
            ticker="AAPL",
            instrument_type="stock",
            fx_required=False,
        )
        assert breakdown.fx == 0.0

    def test_fx_applied_when_required(self, profile):
        engine = CostEngine(profile)
        breakdown = engine.entry_costs(
            price=100.0,
            quantity=10,
            ticker="AAPL",
            instrument_type="stock",
            fx_required=True,
        )
        assert breakdown.fx == pytest.approx(100.0 * 10 * 0.0025)
