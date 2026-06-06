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


class TestVolumBasedSlippage:
    def test_volume_based_basic(self):
        model = SlippageModel(model_type="volume_based", base_pct=0.001, exponent=2.0)
        result = model.calculate(price=100.0, quantity=1000, adv=100000)
        ratio = 1000 / 100000
        expected = 0.001 * (ratio**2.0) * 100.0 * 1000
        assert result == pytest.approx(expected)

    def test_volume_based_no_adv_fallback(self):
        model = SlippageModel(
            model_type="volume_based",
            base_pct=0.001,
            exponent=2.0,
            fixed_pct=0.0005,
        )
        result = model.calculate(price=100.0, quantity=1000, adv=None)
        assert result == pytest.approx(0.0005 * 100.0 * 1000)

    def test_volume_based_zero_adv_fallback(self):
        model = SlippageModel(
            model_type="volume_based",
            base_pct=0.001,
            exponent=2.0,
            fixed_pct=0.0003,
        )
        result = model.calculate(price=100.0, quantity=1000, adv=0.0)
        assert result == pytest.approx(0.0003 * 100.0 * 1000)

    def test_volume_based_no_fallback(self):
        model = SlippageModel(model_type="volume_based", base_pct=0.001, exponent=1.0)
        result = model.calculate(price=100.0, quantity=1000, adv=None)
        assert result == pytest.approx(0.0)
