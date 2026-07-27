import json
from pathlib import Path

import pytest

from phantom.errors import ProfileError
from phantom.profiles.loader import load_profile


def test_load_profile_valid(tmp_path):
    profile_path = tmp_path / "test_broker.json"
    profile_path.write_text(
        json.dumps(
            {
                "profile": {
                    "name": "TEST_BROKER",
                    "min_order_size": 1.0,
                    "max_leverage": 1.0,
                    "supported_instruments": ["stock"],
                    "fx_conversion_pct": 0.001,
                    "fx_base_currency": "USD",
                },
                "commission": {"model_type": "fixed", "fixed_fee": 1.0},
                "spread": {"model_type": "fixed", "fixed_spread_pct": 0.0005},
                "slippage": {"model_type": "fixed_pct", "fixed_pct": 0.0001},
                "overnight": {
                    "long_markup_pct": 0.0,
                    "short_markup_pct": 0.0,
                    "day_divisor": 365,
                    "rate_source": "manual",
                    "manual_rate": 0.0,
                },
                "margin": {
                    "default_margin_pct": 1.0,
                    "margin_call_level": 1.0,
                    "stop_out_level": 0.5,
                },
                "dividend": {
                    "withholding_rates": {"US": 0.15},
                    "cfd_dividend_adjustment": 1.0,
                    "cfd_short_dividend_charge": 1.0,
                },
                "trading_hours": {
                    "timezone": "America/New_York",
                    "open": "09:30",
                    "close": "16:00",
                    "pre_market": False,
                    "post_market": False,
                },
            }
        )
    )
    profile = load_profile(profile_path)
    assert profile.name == "TEST_BROKER"
    assert profile.fx_conversion_pct == 0.001


def test_load_profile_missing_file():
    with pytest.raises(ProfileError, match="Profile file not found"):
        load_profile("/nonexistent/path.json")


def test_load_profile_invalid_json(tmp_path):
    profile_path = tmp_path / "bad.json"
    profile_path.write_text("{ invalid json")
    with pytest.raises(ProfileError, match="Invalid JSON"):
        load_profile(profile_path)


def test_load_profile_missing_required_field(tmp_path):
    profile_path = tmp_path / "incomplete.json"
    profile_path.write_text(json.dumps({"profile": {"name": "INCOMPLETE"}}))
    with pytest.raises(ProfileError, match="Validation failed"):
        load_profile(profile_path)


def test_load_profile_degiro():
    profile_path = (
        Path(__file__).parent.parent.parent / "src" / "phantom" / "profiles" / "degiro.json"
    )
    profile = load_profile(profile_path)
    assert profile.name == "DEGIRO"
    assert profile.commission.model_type == "fixed"
    assert profile.spread.model_type == "dynamic"
    assert profile.fx_base_currency == "EUR"


def test_load_profile_ibkr_commission_is_nonzero():
    # Regression test for a bug where ibkr.json's commission block used a
    # min_volume/max_volume/per_share schema that doesn't match the
    # "tiered" model_type's expected up_to/rate keys. CommissionModel.calculate()
    # silently fell back to tier.get("rate", 0.0) == 0.0 for every trade,
    # meaning every simulated IBKR trade paid zero commission. The fix
    # switched the profile to model_type "per_share" (which IBKR's real
    # per-share fee structure actually matches) with a flat rate. This test
    # loads the real bundled ibkr.json so it would have caught the bug.
    profile_path = (
        Path(__file__).parent.parent.parent / "src" / "phantom" / "profiles" / "ibkr.json"
    )
    profile = load_profile(profile_path)
    assert profile.name == "IBKR"
    assert profile.commission.model_type == "per_share"
    commission = profile.commission.calculate(quantity=100, price=50.0, monthly_volume=0)
    assert commission > 0.0
