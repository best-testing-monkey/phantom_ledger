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
