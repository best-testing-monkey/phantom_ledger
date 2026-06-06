import pytest

from phantom.models.broker import CommissionModel


class TestFixedCommission:
    def test_flat_fee_applied(self):
        model = CommissionModel(model_type="fixed", fixed_fee=1.0)
        assert model.calculate(quantity=10, price=185.0, monthly_volume=0) == 1.0

    def test_flat_fee_independent_of_quantity(self):
        model = CommissionModel(model_type="fixed", fixed_fee=2.50)
        assert model.calculate(quantity=1, price=100.0, monthly_volume=0) == 2.50
        assert model.calculate(quantity=1000, price=100.0, monthly_volume=0) == 2.50

    def test_flat_fee_independent_of_price(self):
        model = CommissionModel(model_type="fixed", fixed_fee=1.0)
        assert model.calculate(quantity=10, price=50.0, monthly_volume=0) == 1.0
        assert model.calculate(quantity=10, price=500.0, monthly_volume=0) == 1.0

    def test_zero_fee(self):
        model = CommissionModel(model_type="fixed", fixed_fee=0.0)
        assert model.calculate(quantity=10, price=185.0, monthly_volume=0) == 0.0


class TestPerShareCommission:
    def test_basic_per_share(self):
        model = CommissionModel(model_type="per_share", per_share=0.10, per_share_min=1.0)
        result = model.calculate(quantity=15, price=100.0, monthly_volume=0)
        assert result == pytest.approx(1.5)

    def test_per_share_with_minimum(self):
        model = CommissionModel(model_type="per_share", per_share=0.10, per_share_min=5.0)
        result = model.calculate(quantity=10, price=100.0, monthly_volume=0)
        assert result == pytest.approx(5.0)

    def test_per_share_with_max_pct(self):
        model = CommissionModel(
            model_type="per_share",
            per_share=0.10,
            per_share_min=0.0,
            per_share_max_pct=0.005,
        )
        result = model.calculate(quantity=100, price=100.0, monthly_volume=0)
        expected = min(10.0, 0.005 * 100.0 * 100)
        assert result == pytest.approx(expected)

    def test_per_share_zero_rate(self):
        model = CommissionModel(model_type="per_share", per_share=0.0)
        result = model.calculate(quantity=100, price=50.0, monthly_volume=0)
        assert result == pytest.approx(0.0)


class TestTieredCommission:
    def test_tiered_basic(self):
        model = CommissionModel(
            model_type="tiered",
            tiers=[
                {"up_to": 10000, "rate": 0.002},
                {"up_to": 50000, "rate": 0.0015},
                {"up_to": float("inf"), "rate": 0.001},
            ],
        )
        result = model.calculate(quantity=100, price=50.0, monthly_volume=5000)
        expected = 100 * 50 * 0.002
        assert result == pytest.approx(expected)

    def test_tiered_middle_tier(self):
        model = CommissionModel(
            model_type="tiered",
            tiers=[
                {"up_to": 10000, "rate": 0.002},
                {"up_to": 50000, "rate": 0.0015},
                {"up_to": float("inf"), "rate": 0.001},
            ],
        )
        result = model.calculate(quantity=100, price=50.0, monthly_volume=25000)
        expected = 100 * 50 * 0.0015
        assert result == pytest.approx(expected)

    def test_tiered_highest_tier(self):
        model = CommissionModel(
            model_type="tiered",
            tiers=[
                {"up_to": 10000, "rate": 0.002},
                {"up_to": 50000, "rate": 0.0015},
                {"up_to": float("inf"), "rate": 0.001},
            ],
        )
        result = model.calculate(quantity=100, price=50.0, monthly_volume=100000)
        expected = 100 * 50 * 0.001
        assert result == pytest.approx(expected)

    def test_tiered_empty_tiers(self):
        model = CommissionModel(model_type="tiered", tiers=[])
        result = model.calculate(quantity=100, price=50.0, monthly_volume=0)
        assert result == pytest.approx(0.0)


class TestZeroCommission:
    def test_zero_below_threshold(self):
        model = CommissionModel(model_type="zero", monthly_free_volume=10000.0, fixed_fee=5.0)
        result = model.calculate(quantity=100, price=50.0, monthly_volume=5000)
        assert result == pytest.approx(0.0)

    def test_zero_above_threshold_fixed(self):
        model = CommissionModel(model_type="zero", monthly_free_volume=10000.0, fixed_fee=5.0)
        result = model.calculate(quantity=100, price=50.0, monthly_volume=15000)
        assert result == pytest.approx(5.0)

    def test_zero_above_threshold_per_share(self):
        model = CommissionModel(model_type="zero", monthly_free_volume=10000.0, per_share=0.10)
        result = model.calculate(quantity=100, price=50.0, monthly_volume=15000)
        expected = 100 * 0.10
        assert result == pytest.approx(expected)

    def test_zero_no_threshold(self):
        model = CommissionModel(model_type="zero")
        result = model.calculate(quantity=100, price=50.0, monthly_volume=1000000)
        assert result == pytest.approx(0.0)
