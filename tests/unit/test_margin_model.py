from phantom.models.broker import MarginClassRule, MarginModel


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
