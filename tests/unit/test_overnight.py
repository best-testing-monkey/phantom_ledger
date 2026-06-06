import pytest

from phantom.models.broker import OvernightModel


class TestOvernightModel:
    def test_long_basic(self):
        model = OvernightModel(
            long_markup_pct=0.01,
            short_markup_pct=0.02,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.05,
        )
        result = model.calculate(
            notional=10000.0, direction="long", reference_rate=0.05, day_of_week=1
        )
        expected = 10000.0 * (0.05 + 0.01) / 365
        assert result == pytest.approx(expected)

    def test_short_basic(self):
        model = OvernightModel(
            long_markup_pct=0.01,
            short_markup_pct=0.02,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.05,
        )
        result = model.calculate(
            notional=10000.0, direction="short", reference_rate=0.05, day_of_week=1
        )
        expected = 10000.0 * (0.05 + 0.02) / 365
        assert result == pytest.approx(expected)

    def test_wednesday_triple_swap(self):
        model = OvernightModel(
            long_markup_pct=0.01,
            short_markup_pct=0.02,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.05,
        )
        result = model.calculate(
            notional=10000.0, direction="long", reference_rate=0.05, day_of_week=2
        )
        base_charge = 10000.0 * (0.05 + 0.01) / 365
        expected = base_charge * 3
        assert result == pytest.approx(expected)

    def test_zero_rate_zero_markup(self):
        model = OvernightModel(
            long_markup_pct=0.0,
            short_markup_pct=0.0,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.0,
        )
        result = model.calculate(
            notional=10000.0, direction="long", reference_rate=0.0, day_of_week=1
        )
        assert result == pytest.approx(0.0)
