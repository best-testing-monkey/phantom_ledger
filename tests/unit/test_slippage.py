import pytest

from phantom.models.broker import SlippageModel


class TestSlippageModel:
    def test_fixed_pct_basic(self):
        model = SlippageModel(model_type="fixed_pct", fixed_pct=0.0003)
        result = model.calculate(price=185.0, quantity=10)
        assert result == pytest.approx(0.555)

    def test_zero_slippage(self):
        model = SlippageModel(model_type="fixed_pct", fixed_pct=0.0)
        assert model.calculate(price=185.0, quantity=10) == 0.0
