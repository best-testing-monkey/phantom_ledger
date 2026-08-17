from pathlib import Path

import pytest

from phantom.models.broker import MarginClassRule, MarginModel
import phantom.profiles
from phantom.profiles.loader import load_profile

PROFILES_DIR = Path(phantom.profiles.__file__).parent


def test_margin_pct_for_matches_regex_class():
    margin = MarginModel(
        default_margin_pct=0.2,
        margin_call_level=1.5,
        stop_out_level=1.0,
        classes=[MarginClassRule(label="fx", match="^[A-Z]{6}$", margin_pct=0.03)],
    )

    assert margin.margin_pct_for("EURUSD") == 0.03


def test_margin_pct_for_falls_back_to_default_when_no_class_matches():
    margin = MarginModel(
        default_margin_pct=0.2,
        margin_call_level=1.5,
        stop_out_level=1.0,
        classes=[MarginClassRule(label="fx", match="^[A-Z]{6}$", margin_pct=0.03)],
    )

    assert margin.margin_pct_for("AAPL") == 0.2


def test_margin_pct_for_matches_explicit_symbols_list():
    margin = MarginModel(
        default_margin_pct=0.2,
        margin_call_level=1.5,
        stop_out_level=1.0,
        classes=[MarginClassRule(label="indices", symbols=["SPX500", "NAS100"], margin_pct=0.05)],
    )

    assert margin.margin_pct_for("SPX500") == 0.05
    assert margin.margin_pct_for("NAS100") == 0.05
    assert margin.margin_pct_for("AAPL") == 0.2


def test_margin_pct_for_empty_classes_always_returns_default():
    margin = MarginModel(
        default_margin_pct=0.2,
        margin_call_level=1.5,
        stop_out_level=1.0,
    )

    assert margin.classes == []
    assert margin.margin_pct_for("EURUSD") == 0.2
    assert margin.margin_pct_for("AAPL") == 0.2
    assert margin.margin_pct_for("BTCUSD") == 0.2


@pytest.mark.parametrize("profile_name", ["ibkr", "degiro", "xtb"])
def test_bundled_profile_classes_match_yfinance_style_tickers(profile_name):
    """E17-S08 regression: bundled `classes` must also recognize yfinance-style
    tickers (=X FX suffix, =F futures suffix, ^ index prefix, - crypto suffix),
    not just broker-house-native spellings — otherwise every such caller's
    orders silently fall through to `default_margin_pct`.
    """
    profile = load_profile(PROFILES_DIR / f"{profile_name}.json")
    margin = profile.margin

    # yfinance-style conventions (the gap this ticket closes)
    assert margin.margin_pct_for("EURUSD=X") == 0.03  # fx_majors
    assert margin.margin_pct_for("GC=F") == 0.05  # index_commodity (gold futures)
    assert margin.margin_pct_for("CL=F") == 0.10  # other_commodity (crude futures)
    assert margin.margin_pct_for("SI=F") == 0.10  # other_commodity (silver futures)
    assert margin.margin_pct_for("^GSPC") == 0.05  # index_commodity (S&P 500)
    assert margin.margin_pct_for("^DJI") == 0.05  # index_commodity (Dow)
    assert margin.margin_pct_for("^IXIC") == 0.05  # index_commodity (Nasdaq)
    assert margin.margin_pct_for("^FTSE") == 0.05  # index_commodity (UK)
    assert margin.margin_pct_for("^GDAXI") == 0.05  # index_commodity (Germany/DAX)
    assert margin.margin_pct_for("BTC-USD") == 1.0  # crypto
    assert margin.margin_pct_for("ETH-EUR") == 1.0  # crypto


@pytest.mark.parametrize("profile_name", ["ibkr", "degiro", "xtb"])
def test_bundled_profile_classes_native_symbols_still_match(profile_name):
    """Additive-only regression guard: broker-house-native spellings that
    matched before E17-S08 must still match unchanged.
    """
    profile = load_profile(PROFILES_DIR / f"{profile_name}.json")
    margin = profile.margin

    assert margin.margin_pct_for("EURUSD") == 0.03  # fx_majors (native)
    assert margin.margin_pct_for("GOLD") == 0.05  # index_commodity (native)
    assert margin.margin_pct_for("SPX500") == 0.05  # index_commodity (native)
    assert margin.margin_pct_for("OIL") == 0.10  # other_commodity (native)
    assert margin.margin_pct_for("SILVER") == 0.10  # other_commodity (native)
    assert margin.margin_pct_for("BTC") == 1.0  # crypto (native, bare)
