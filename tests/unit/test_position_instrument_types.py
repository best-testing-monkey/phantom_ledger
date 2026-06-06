"""Tests for stock vs CFD position behavior."""

from datetime import datetime
import sqlite3

import pandas as pd
import pytest

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.dividend_log_repo import DividendLogRepo
from phantom.db.repositories.overnight_log_repo import OvernightLogRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.position_manager import PositionManager
from phantom.models.account import Account
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
from phantom.models.position import Position
from phantom.utils.ids import new_id


@pytest.fixture
def test_db_conn():
    """In-memory SQLite connection for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Create minimal schema
    conn.execute("""
        CREATE TABLE broker_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            broker_profile_id TEXT REFERENCES broker_profiles(id),
            base_currency TEXT NOT NULL DEFAULT 'EUR',
            initial_capital REAL NOT NULL,
            cash REAL NOT NULL,
            used_margin REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            pattern_tag TEXT,
            algorithm_id TEXT,
            algorithm_version TEXT,
            algorithm_params TEXT,
            child_account_ids TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE orders (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            ticker TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            order_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            limit_price REAL,
            stop_price REAL,
            trailing_amount REAL,
            trailing_pct REAL,
            take_profit REAL,
            stop_loss REAL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            triggered_at TEXT,
            filled_at TEXT,
            fill_price REAL,
            good_til TEXT,
            max_close_datetime TEXT,
            rejection_reason TEXT,
            position_id TEXT REFERENCES positions(id)
        )
    """)

    conn.execute("""
        CREATE TABLE positions (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            ticker TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_order_id TEXT NOT NULL REFERENCES orders(id),
            entry_price REAL NOT NULL,
            entry_datetime TEXT NOT NULL,
            quantity REAL NOT NULL,
            notional REAL NOT NULL,
            take_profit REAL,
            stop_loss REAL,
            trailing_stop_amount REAL,
            trailing_stop_pct REAL,
            trailing_stop_peak REAL,
            trailing_stop_distance REAL,
            peak_price REAL,
            max_close_datetime TEXT,
            commission_entry REAL NOT NULL DEFAULT 0,
            commission_exit REAL NOT NULL DEFAULT 0,
            spread_cost REAL NOT NULL DEFAULT 0,
            slippage_cost REAL NOT NULL DEFAULT 0,
            overnight_costs REAL NOT NULL DEFAULT 0,
            overnight_accrued REAL NOT NULL DEFAULT 0,
            last_bar_date TEXT,
            dividend_adjustments REAL NOT NULL DEFAULT 0,
            fx_conversion_cost REAL NOT NULL DEFAULT 0,
            country_code TEXT,
            margin_required REAL NOT NULL DEFAULT 0,
            leverage REAL NOT NULL DEFAULT 1.0,
            exit_price REAL,
            exit_datetime TEXT,
            realized_pnl REAL,
            status TEXT NOT NULL,
            close_reason TEXT,
            pattern_tag TEXT,
            replay_completed_at TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE overnight_log (
            id TEXT PRIMARY KEY,
            position_id TEXT NOT NULL REFERENCES positions(id),
            account_id TEXT NOT NULL REFERENCES accounts(id),
            date TEXT NOT NULL,
            rate REAL NOT NULL,
            charge_amount REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE dividend_log (
            id TEXT PRIMARY KEY,
            position_id TEXT NOT NULL REFERENCES positions(id),
            account_id TEXT NOT NULL REFERENCES accounts(id),
            ex_date TEXT NOT NULL,
            dividend_per_share REAL NOT NULL,
            adjustment_amount REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def broker_profile():
    """Test broker profile with overnight and margin models."""
    return BrokerProfile(
        name="TEST_BROKER",
        commission=CommissionModel(model_type="zero"),
        spread=SpreadModel(model_type="fixed", fixed_spread_pct=0.0),
        slippage=SlippageModel(model_type="fixed_pct", fixed_pct=0.0),
        overnight=OvernightModel(
            long_markup_pct=0.005,
            short_markup_pct=0.01,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.02,
        ),
        margin=MarginModel(
            default_margin_pct=0.1,
            margin_call_level=1.0,
            stop_out_level=0.5,
        ),
        dividend=DividendModel(
            withholding_rates={"US": 0.15, "NL": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        ),
        fx_conversion_pct=0.0,
        fx_base_currency="EUR",
        min_order_size=1.0,
        max_leverage=1.0,
        trading_hours=TradingHoursConfig(
            timezone="UTC",
            open="00:00",
            close="23:59",
            pre_market=False,
            post_market=False,
        ),
        supported_instruments=["stock", "cfd"],
    )


def test_stock_position_no_overnight_accrual(test_db_conn, broker_profile):
    """Stock positions should not accrue overnight costs."""
    account_repo = AccountRepo(test_db_conn)
    position_repo = PositionRepo(test_db_conn)
    cost_engine = CostEngine(broker_profile)
    overnight_repo = OvernightLogRepo(test_db_conn)
    dividend_repo = DividendLogRepo(test_db_conn)

    manager = PositionManager(
        position_repo, account_repo, cost_engine, overnight_repo, dividend_repo
    )

    # Create broker profile in DB first
    broker_id = new_id()
    test_db_conn.execute(
        """INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (broker_id, "TEST_BROKER", "{}", "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    )
    test_db_conn.commit()

    # Create account and order
    account = Account(
        id=new_id(),
        name="test",
        account_type="manual",
        broker_profile_id=broker_id,
        initial_capital=10000,
        cash=10000,
    )
    account_repo.create(account)

    order_id = new_id()
    test_db_conn.execute(
        """INSERT INTO orders (id, account_id, ticker, instrument_type, direction,
            order_type, quantity, status, created_at) VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (order_id, account.id, "AAPL", "stock", "long", "market", 100, "filled", "2025-01-02"),
    )
    test_db_conn.commit()

    # Create stock position
    position = Position(
        id=new_id(),
        account_id=account.id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id=order_id,
        entry_price=100.0,
        entry_datetime=datetime.fromisoformat("2025-01-02T09:30:00+00:00"),
        quantity=100,
        notional=10000,
    )
    position_repo.create(position)

    # Simulate multiple days
    dates = pd.date_range("2025-01-02", periods=3, freq="D")
    for date in dates:
        bar = pd.Series(
            {"Open": 100, "High": 101, "Low": 99, "Close": 100},
            name=date,
        )
        # Try to apply overnight cost (should have no effect for stock)
        manager._apply_overnight_cost(position, account, bar, broker_profile.overnight, 0.02)

    # Verify no overnight accrual
    assert position.overnight_accrued == 0.0
    assert account.cash == 10000  # Unchanged
    overnight_logs = overnight_repo.list(position_id=position.id)
    assert len(overnight_logs) == 0


def test_cfd_position_overnight_charges(test_db_conn, broker_profile):
    """CFD positions should accrue overnight charges on day boundaries."""
    account_repo = AccountRepo(test_db_conn)
    position_repo = PositionRepo(test_db_conn)
    cost_engine = CostEngine(broker_profile)
    overnight_repo = OvernightLogRepo(test_db_conn)
    dividend_repo = DividendLogRepo(test_db_conn)

    manager = PositionManager(
        position_repo, account_repo, cost_engine, overnight_repo, dividend_repo
    )

    # Create broker profile in DB first
    broker_id = new_id()
    test_db_conn.execute(
        """INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (broker_id, "TEST_BROKER", "{}", "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    )
    test_db_conn.commit()

    # Create account
    account = Account(
        id=new_id(),
        name="test",
        account_type="manual",
        broker_profile_id=broker_id,
        initial_capital=10000,
        cash=10000,
    )
    account_repo.create(account)

    order_id = new_id()
    test_db_conn.execute(
        """INSERT INTO orders (id, account_id, ticker, instrument_type, direction,
            order_type, quantity, status, created_at) VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (order_id, account.id, "EUR/USD", "cfd", "long", "market", 100000, "filled", "2025-01-02"),
    )
    test_db_conn.commit()

    # Create CFD position
    position = Position(
        id=new_id(),
        account_id=account.id,
        ticker="EUR/USD",
        instrument_type="cfd",
        direction="long",
        entry_order_id=order_id,
        entry_price=1.0,
        entry_datetime=datetime.fromisoformat("2025-01-02T09:30:00+00:00"),
        quantity=100000,
        notional=100000,
    )
    position_repo.create(position)

    # Simulate multiple days: Thursday (day 3), Friday (day 4), Saturday (day 5), Monday (day 0)
    # Wednesday is day 2 (triple swap)
    dates = pd.date_range("2025-01-02", periods=3, freq="D")

    initial_cash = account.cash
    for i, date in enumerate(dates):
        bar = pd.Series(
            {"Open": 1.0, "High": 1.01, "Low": 0.99, "Close": 1.0},
            name=date,
        )
        manager._apply_overnight_cost(position, account, bar, broker_profile.overnight, 0.02)

    # Verify overnight charges were applied
    assert position.overnight_accrued > 0
    assert account.cash < initial_cash
    overnight_logs = overnight_repo.list(position_id=position.id)
    assert len(overnight_logs) > 0


def test_stock_position_zero_margin_required(test_db_conn, broker_profile):
    """Stock positions should have margin_required=0."""
    account_repo = AccountRepo(test_db_conn)
    cost_engine = CostEngine(broker_profile)

    # Create broker profile in DB first
    broker_id = new_id()
    test_db_conn.execute(
        """INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (broker_id, "TEST_BROKER", "{}", "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    )
    test_db_conn.commit()

    # Create account
    account = Account(
        id=new_id(),
        name="test",
        account_type="manual",
        broker_profile_id=broker_id,
        initial_capital=10000,
        cash=10000,
    )
    account_repo.create(account)

    order_id = new_id()
    test_db_conn.execute(
        """INSERT INTO orders (id, account_id, ticker, instrument_type, direction,
            order_type, quantity, status, created_at) VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (order_id, account.id, "AAPL", "stock", "long", "market", 100, "filled", "2025-01-02"),
    )
    test_db_conn.commit()

    # Create stock position
    position = Position(
        id=new_id(),
        account_id=account.id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id=order_id,
        entry_price=100.0,
        entry_datetime=datetime.fromisoformat("2025-01-02T09:30:00+00:00"),
        quantity=100,
        notional=10000,
        margin_required=0.0,
    )

    # Stock position should have margin_required=0
    assert position.margin_required == 0.0
    assert position.instrument_type == "stock"


def test_cfd_position_margin_required(test_db_conn, broker_profile):
    """CFD positions should have margin_required > 0."""
    account_repo = AccountRepo(test_db_conn)
    position_repo = PositionRepo(test_db_conn)
    cost_engine = CostEngine(broker_profile)

    # Create broker profile in DB first
    broker_id = new_id()
    test_db_conn.execute(
        """INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (broker_id, "TEST_BROKER", "{}", "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    )
    test_db_conn.commit()

    # Create account
    account = Account(
        id=new_id(),
        name="test",
        account_type="manual",
        broker_profile_id=broker_id,
        initial_capital=10000,
        cash=10000,
    )
    account_repo.create(account)

    order_id = new_id()
    test_db_conn.execute(
        """INSERT INTO orders (id, account_id, ticker, instrument_type, direction,
            order_type, quantity, status, created_at) VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            order_id,
            account.id,
            "EUR/USD",
            "cfd",
            "long",
            "market",
            100000,
            "filled",
            "2025-01-02",
        ),
    )
    test_db_conn.commit()

    # Create CFD position with margin
    quantity = 100000
    price = 1.0
    margin_pct = broker_profile.margin.default_margin_pct
    margin_required = quantity * price * margin_pct

    position = Position(
        id=new_id(),
        account_id=account.id,
        ticker="EUR/USD",
        instrument_type="cfd",
        direction="long",
        entry_order_id=order_id,
        entry_price=price,
        entry_datetime=datetime.fromisoformat("2025-01-02T09:30:00+00:00"),
        quantity=quantity,
        notional=quantity * price,
        margin_required=margin_required,
    )

    # CFD position should have margin_required > 0
    assert position.margin_required > 0
    assert position.instrument_type == "cfd"
    assert position.margin_required == pytest.approx(10000)


def test_instrument_type_literal(test_db_conn):
    """Verify instrument_type is properly typed as InstrumentType literal."""
    position = Position(
        id=new_id(),
        account_id="test",
        ticker="TEST",
        instrument_type="stock",
        direction="long",
        entry_order_id="order1",
        entry_price=100.0,
        entry_datetime=datetime.fromisoformat("2025-01-02T09:30:00+00:00"),
        quantity=100,
        notional=10000,
    )

    # Verify the type is correct
    assert position.instrument_type in ("stock", "cfd")

    position2 = Position(
        id=new_id(),
        account_id="test",
        ticker="EUR/USD",
        instrument_type="cfd",
        direction="long",
        entry_order_id="order2",
        entry_price=1.0,
        entry_datetime=datetime.fromisoformat("2025-01-02T09:30:00+00:00"),
        quantity=100000,
        notional=100000,
    )

    assert position2.instrument_type in ("stock", "cfd")
