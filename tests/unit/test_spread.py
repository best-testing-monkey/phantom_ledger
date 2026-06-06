import pytest

from phantom.models.broker import SpreadModel


class TestSpreadModel:
    def test_fixed_basic(self):
        model = SpreadModel(model_type="fixed", fixed_spread_pct=0.0005)
        result = model.calculate(price=100.0, quantity=10)
        assert result == pytest.approx(0.5)

    def test_dynamic_basic_with_atr(self):
        model = SpreadModel(
            model_type="dynamic",
            base_spread_pct=0.0005,
            volatility_multiplier=0.3,
            time_of_day_curve={"0": 1.0, "9": 1.2, "14": 0.8},
        )
        result = model.calculate(price=100.0, quantity=10, atr=1.0, hour_utc=14)
        expected = 0.0005 * 0.8 * (1 + 0.3 * 1.0 / 100.0) * 100.0 * 10
        assert result == pytest.approx(expected)

    def test_dynamic_without_atr(self):
        model = SpreadModel(
            model_type="dynamic",
            base_spread_pct=0.0005,
            volatility_multiplier=0.3,
            time_of_day_curve={"0": 1.0},
        )
        result = model.calculate(price=100.0, quantity=10, atr=None, hour_utc=0)
        expected = 0.0005 * 1.0 * 1.0 * 100.0 * 10
        assert result == pytest.approx(expected)

    def test_zero_fixed_spread(self):
        model = SpreadModel(model_type="fixed", fixed_spread_pct=0.0)
        assert model.calculate(price=100.0, quantity=10) == 0.0
