import sqlite3

import numpy as np
import pandas as pd
import pytest

from phantom import Phantom
from phantom.db.database import run_migrations
from phantom.models.broker import (
    BrokerProfile,
    CommissionModel,
    DividendModel,
    MarginModel,
    OvernightModel,
    SlippageModel,
    SpreadModel,
    TradingHoursConfig,
)


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def phantom_instance(tmp_path):
    return Phantom(data_dir=str(tmp_path), in_memory=True)


@pytest.fixture
def degiro_profile():
    return BrokerProfile(
        name="DEGIRO_TEST",
        commission=CommissionModel(model_type="fixed", fixed_fee=1.0),
        spread=SpreadModel(model_type="fixed", fixed_spread_pct=0.0005),
        slippage=SlippageModel(model_type="fixed_pct", fixed_pct=0.0003),
        overnight=OvernightModel(
            long_markup_pct=0.0,
            short_markup_pct=0.0,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.0,
        ),
        margin=MarginModel(
            default_margin_pct=1.0,
            margin_call_level=1.0,
            stop_out_level=0.5,
        ),
        dividend=DividendModel(
            withholding_rates={"US": 0.15, "NL": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        ),
        fx_conversion_pct=0.0025,
        fx_base_currency="EUR",
        min_order_size=1.0,
        max_leverage=1.0,
        trading_hours=TradingHoursConfig(
            timezone="America/New_York",
            open="09:30",
            close="16:00",
            pre_market=False,
            post_market=False,
        ),
        supported_instruments=["stock", "etf"],
    )


@pytest.fixture
def sample_price_data():
    dates = pd.bdate_range("2025-01-02", periods=20)
    base = 185.0
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(20).cumsum() * 0.5
    closes = base + noise
    return pd.DataFrame(
        {
            "Open": closes - rng.random(20) * 0.5,
            "High": closes + rng.random(20) * 1.0,
            "Low": closes - rng.random(20) * 1.0,
            "Close": closes,
            "Adj Close": closes,
            "Volume": rng.integers(1_000_000, 10_000_000, 20),
        },
        index=dates,
    )
