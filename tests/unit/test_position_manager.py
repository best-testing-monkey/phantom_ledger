import pandas as pd
import pytest

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.position_manager import PositionManager, resolve_tp_sl_conflict
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
from phantom.utils.datetime import now_utc, to_iso
from phantom.utils.ids import new_id


@pytest.fixture
def test_profile():
    return BrokerProfile(
        name="TEST",
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
def position_manager(db_conn, test_profile):
    position_repo = PositionRepo(db_conn)
    account_repo = AccountRepo(db_conn)
    cost_engine = CostEngine(test_profile)
    return PositionManager(position_repo, account_repo, cost_engine)


def _setup_account_and_position(db_conn, position_repo):
    bid = new_id()
    db_conn.execute(
        "INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (bid, "TEST", "{}", to_iso(now_utc()), to_iso(now_utc())),
    )
    aid = new_id()
    db_conn.execute(
        "INSERT INTO accounts (id, name, account_type, broker_profile_id, base_currency, initial_capital, cash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, "acct", "manual", bid, "EUR", 10000.0, 10000.0, to_iso(now_utc())),
    )
    oid = new_id()
    db_conn.execute(
        "INSERT INTO orders (id, account_id, ticker, instrument_type, direction, order_type, quantity, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (oid, aid, "AAPL", "stock", "long", "market", 10.0, "filled", to_iso(now_utc())),
    )
    db_conn.commit()

    pos = Position(
        account_id=aid,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        take_profit=160.0,
        stop_loss=140.0,
    )
    position_repo.create(pos)
    return pos, aid


def test_update_long_unrealized_pnl(position_manager, db_conn):
    position_repo = PositionRepo(db_conn)
    pos, _ = _setup_account_and_position(db_conn, position_repo)

    bar = pd.Series(
        {
            "Open": 150.0,
            "High": 155.0,
            "Low": 149.0,
            "Close": 155.0,
        },
        name=pd.Timestamp("2025-01-02"),
    )

    updated, should_close = position_manager.update(pos, bar)
    assert updated is pos
    assert should_close is False


def test_update_short_unrealized_pnl(position_manager, db_conn):
    position_repo = PositionRepo(db_conn)
    aid = new_id()
    bid = new_id()
    db_conn.execute(
        "INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (bid, "TEST", "{}", to_iso(now_utc()), to_iso(now_utc())),
    )
    db_conn.execute(
        "INSERT INTO accounts (id, name, account_type, broker_profile_id, base_currency, initial_capital, cash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, "acct", "manual", bid, "EUR", 10000.0, 10000.0, to_iso(now_utc())),
    )
    oid = new_id()
    db_conn.execute(
        "INSERT INTO orders (id, account_id, ticker, instrument_type, direction, order_type, quantity, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (oid, aid, "AAPL", "stock", "short", "market", 10.0, "filled", to_iso(now_utc())),
    )
    db_conn.commit()

    pos = Position(
        account_id=aid,
        ticker="AAPL",
        instrument_type="stock",
        direction="short",
        entry_order_id=oid,
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        take_profit=140.0,
        stop_loss=160.0,
    )
    position_repo.create(pos)

    bar = pd.Series(
        {
            "Open": 150.0,
            "High": 155.0,
            "Low": 145.0,
            "Close": 145.0,
        },
        name=pd.Timestamp("2025-01-02"),
    )

    updated, should_close = position_manager.update(pos, bar)
    assert updated is pos
    assert should_close is False


def test_tp_triggers_on_long(position_manager, db_conn):
    position_repo = PositionRepo(db_conn)
    pos, _ = _setup_account_and_position(db_conn, position_repo)

    bar = pd.Series(
        {
            "Open": 155.0,
            "High": 161.0,
            "Low": 155.0,
            "Close": 160.0,
        },
        name=pd.Timestamp("2025-01-02"),
    )

    _, should_close = position_manager.update(pos, bar)
    assert should_close is True

    result = position_manager.determine_close(pos, bar)
    assert result is not None
    assert result[0] == 160.0
    assert result[1] == "tp"


def test_sl_triggers_on_long(position_manager, db_conn):
    position_repo = PositionRepo(db_conn)
    pos, _ = _setup_account_and_position(db_conn, position_repo)

    bar = pd.Series(
        {
            "Open": 145.0,
            "High": 145.0,
            "Low": 138.0,
            "Close": 140.0,
        },
        name=pd.Timestamp("2025-01-02"),
    )

    _, should_close = position_manager.update(pos, bar)
    assert should_close is True

    result = position_manager.determine_close(pos, bar)
    assert result is not None
    assert result[0] == 140.0
    assert result[1] == "sl"


def test_tp_triggers_on_short(position_manager, db_conn):
    position_repo = PositionRepo(db_conn)
    aid = new_id()
    bid = new_id()
    db_conn.execute(
        "INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (bid, "TEST", "{}", to_iso(now_utc()), to_iso(now_utc())),
    )
    db_conn.execute(
        "INSERT INTO accounts (id, name, account_type, broker_profile_id, base_currency, initial_capital, cash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, "acct", "manual", bid, "EUR", 10000.0, 10000.0, to_iso(now_utc())),
    )
    oid = new_id()
    db_conn.execute(
        "INSERT INTO orders (id, account_id, ticker, instrument_type, direction, order_type, quantity, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (oid, aid, "AAPL", "stock", "short", "market", 10.0, "filled", to_iso(now_utc())),
    )
    db_conn.commit()

    pos = Position(
        account_id=aid,
        ticker="AAPL",
        instrument_type="stock",
        direction="short",
        entry_order_id=oid,
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        take_profit=140.0,
        stop_loss=160.0,
    )
    position_repo.create(pos)

    bar = pd.Series(
        {
            "Open": 145.0,
            "High": 145.0,
            "Low": 138.0,
            "Close": 140.0,
        },
        name=pd.Timestamp("2025-01-02"),
    )

    _, should_close = position_manager.update(pos, bar)
    assert should_close is True

    result = position_manager.determine_close(pos, bar)
    assert result is not None
    assert result[0] == 140.0
    assert result[1] == "tp"


def test_no_close_if_no_tp_sl_hit(position_manager, db_conn):
    position_repo = PositionRepo(db_conn)
    pos, _ = _setup_account_and_position(db_conn, position_repo)

    bar = pd.Series(
        {
            "Open": 150.0,
            "High": 152.0,
            "Low": 149.0,
            "Close": 151.0,
        },
        name=pd.Timestamp("2025-01-02"),
    )

    _, should_close = position_manager.update(pos, bar)
    assert should_close is False

    result = position_manager.determine_close(pos, bar)
    assert result is None


def test_max_close_datetime_triggers_close(position_manager, db_conn):
    position_repo = PositionRepo(db_conn)
    aid = new_id()
    bid = new_id()
    max_close = pd.Timestamp("2025-01-02 16:00:00").to_pydatetime()
    db_conn.execute(
        "INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (bid, "TEST", "{}", to_iso(now_utc()), to_iso(now_utc())),
    )
    db_conn.execute(
        "INSERT INTO accounts (id, name, account_type, broker_profile_id, base_currency, initial_capital, cash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, "acct", "manual", bid, "EUR", 10000.0, 10000.0, to_iso(now_utc())),
    )
    oid = new_id()
    db_conn.execute(
        "INSERT INTO orders (id, account_id, ticker, instrument_type, direction, order_type, quantity, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (oid, aid, "AAPL", "stock", "long", "market", 10.0, "filled", to_iso(now_utc())),
    )
    db_conn.commit()

    pos = Position(
        account_id=aid,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        max_close_datetime=max_close,
    )
    position_repo.create(pos)

    bar = pd.Series(
        {
            "Open": 150.0,
            "High": 152.0,
            "Low": 149.0,
            "Close": 151.0,
        },
        name=pd.Timestamp("2025-01-02 16:00:00"),
    )

    _, should_close = position_manager.update(pos, bar)
    assert should_close is True

    result = position_manager.determine_close(pos, bar)
    assert result is not None
    assert result[0] == 151.0
    assert result[1] == "max_time"


def test_resolve_tp_sl_conservative():
    pos = Position(
        account_id="test",
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id="oid",
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        take_profit=160.0,
        stop_loss=140.0,
    )
    bar = pd.Series({"Open": 150.0})
    result = resolve_tp_sl_conflict(pos, bar, "conservative")
    assert result == "sl"


def test_resolve_tp_sl_optimistic():
    pos = Position(
        account_id="test",
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id="oid",
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        take_profit=160.0,
        stop_loss=140.0,
    )
    bar = pd.Series({"Open": 150.0})
    result = resolve_tp_sl_conflict(pos, bar, "optimistic")
    assert result == "tp"


def test_resolve_tp_sl_proximity_closer_to_tp():
    pos = Position(
        account_id="test",
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id="oid",
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        take_profit=152.0,
        stop_loss=140.0,
    )
    bar = pd.Series({"Open": 150.0})
    result = resolve_tp_sl_conflict(pos, bar, "proximity")
    assert result == "tp"


def test_resolve_tp_sl_proximity_closer_to_sl():
    pos = Position(
        account_id="test",
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id="oid",
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        take_profit=160.0,
        stop_loss=142.0,
    )
    bar = pd.Series({"Open": 150.0})
    result = resolve_tp_sl_conflict(pos, bar, "proximity")
    assert result == "sl"


def test_both_tp_and_sl_hit_conservative(position_manager, db_conn):
    position_repo = PositionRepo(db_conn)
    pos, _ = _setup_account_and_position(db_conn, position_repo)

    bar = pd.Series(
        {
            "Open": 150.0,
            "High": 161.0,
            "Low": 138.0,
            "Close": 150.0,
        },
        name=pd.Timestamp("2025-01-02"),
    )

    _, should_close = position_manager.update(pos, bar)
    assert should_close is True

    result = position_manager.determine_close(pos, bar, mode="conservative")
    assert result is not None
    assert result[0] == 140.0
    assert result[1] == "sl"


def test_close_computes_realized_pnl(position_manager, db_conn):
    position_repo = PositionRepo(db_conn)
    pos, _ = _setup_account_and_position(db_conn, position_repo)

    bar_ts = pd.Timestamp("2025-01-02").to_pydatetime()
    closed = position_manager.close(pos, 155.0, "manual", bar_ts)
    assert closed.status == "closed"
    assert closed.exit_price == 155.0
    assert closed.close_reason == "manual"
    assert closed.realized_pnl is not None
    gross_pnl = (155.0 - 150.0) * 10.0
    assert closed.realized_pnl <= gross_pnl
