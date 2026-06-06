import pytest

from phantom.models.broker import DividendModel


class TestDividendModel:
    def test_stock_dividend_us_withholding(self):
        model = DividendModel(
            withholding_rates={"US": 0.15, "NL": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        )
        net_amount, withholding = model.calculate_stock_dividend(100.0, "US")
        assert net_amount == pytest.approx(85.0)
        assert withholding == pytest.approx(15.0)

    def test_stock_dividend_nl_withholding(self):
        model = DividendModel(
            withholding_rates={"US": 0.15, "NL": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        )
        net_amount, withholding = model.calculate_stock_dividend(100.0, "NL")
        assert net_amount == pytest.approx(85.0)
        assert withholding == pytest.approx(15.0)

    def test_stock_dividend_unknown_country(self):
        model = DividendModel(
            withholding_rates={"US": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        )
        net_amount, withholding = model.calculate_stock_dividend(100.0, "GB")
        assert net_amount == pytest.approx(100.0)
        assert withholding == pytest.approx(0.0)

    def test_cfd_long_dividend(self):
        model = DividendModel(
            withholding_rates={"US": 0.15},
            cfd_dividend_adjustment=0.8,
            cfd_short_dividend_charge=1.0,
        )
        result = model.calculate_cfd_adjustment(100.0, "long")
        assert result == pytest.approx(80.0)

    def test_cfd_short_dividend(self):
        model = DividendModel(
            withholding_rates={"US": 0.15},
            cfd_dividend_adjustment=0.8,
            cfd_short_dividend_charge=1.2,
        )
        result = model.calculate_cfd_adjustment(100.0, "short")
        assert result == pytest.approx(-120.0)
