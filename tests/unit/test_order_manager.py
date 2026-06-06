import pandas as pd
import pytest

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.order_repo import OrderRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.order_manager import OrderManager
from phantom.errors import InsufficientFundsError
from phantom.models.account import Account
from phantom.models.broker import (
    BrokerProfile,
)
from phantom.models.order import Order
from phantom.utils.datetime import now_utc


@pytest.fixture
def setup_trading_env(db_conn):
    from phantom.utils.datetime import to_iso
    from phantom.utils.ids import new_id

    account_repo = AccountRepo(db_conn)
    order_repo = OrderRepo(db_conn)
    position_repo = PositionRepo(db_conn)

    broker_id = new_id()
    profile_json = (
        '{"name":"TEST_BROKER","commission":{"model_type":"fixed","fixed_fee":1.0},'
        '"spread":{"model_type":"fixed","fixed_spread_pct":0.0005},'
        '"slippage":{"model_type":"fixed_pct","fixed_pct":0.0003},'
        '"overnight":{"long_markup_pct":0.0,"short_markup_pct":0.0,'
        '"day_divisor":365,"rate_source":"manual","manual_rate":0.0},'
        '"margin":{"default_margin_pct":1.0,"margin_call_level":1.0,"stop_out_level":0.5},'
        '"dividend":{"withholding_rates":{"US":0.15},"cfd_dividend_adjustment":1.0,'
        '"cfd_short_dividend_charge":1.0},'
        '"fx_conversion_pct":0.0025,"fx_base_currency":"USD","min_order_size":1.0,'
        '"max_leverage":1.0,"trading_hours":{"timezone":"America/New_York",'
        '"open":"09:30","close":"16:00","pre_market":false,"post_market":false},'
        '"supported_instruments":["stock"]}'
    )
    db_conn.execute(
        """INSERT INTO broker_profiles
        (id, name, config_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)""",
        (broker_id, "TEST_BROKER", profile_json, to_iso(now_utc()), to_iso(now_utc())),
    )
    db_conn.commit()

    account = Account(
        name="test_account",
        account_type="manual",
        broker_profile_id=broker_id,
        base_currency="USD",
        initial_capital=10000.0,
        cash=10000.0,
    )
    account_repo.create(account)

    profile = BrokerProfile.model_validate_json(profile_json)
    cost_engine = CostEngine(profile)
    manager = OrderManager(order_repo, account_repo, cost_engine)

    return {
        "account": account,
        "manager": manager,
        "order_repo": order_repo,
        "position_repo": position_repo,
        "account_repo": account_repo,
    }


def test_place_market_order(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=10.0,
    )

    placed = env["manager"].place(env["account"].id, order)
    assert placed.status == "pending"
    assert placed.account_id == env["account"].id


def test_place_limit_order_sufficient_funds(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="limit",
        quantity=10.0,
        limit_price=100.0,
    )

    placed = env["manager"].place(env["account"].id, order)
    assert placed.status == "pending"


def test_place_limit_order_insufficient_funds(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="limit",
        quantity=1000.0,
        limit_price=100.0,
    )

    with pytest.raises(InsufficientFundsError):
        env["manager"].place(env["account"].id, order)


def test_evaluate_market_order(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=10.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    dates = pd.DatetimeIndex(["2025-01-02"])
    df = pd.DataFrame(
        {
            "Open": [150.0],
            "High": [151.0],
            "Low": [149.0],
            "Close": [150.5],
        },
        index=dates,
    )
    bar = df.iloc[0]

    filled = env["manager"].evaluate(bar, [placed])
    assert len(filled) == 1
    assert filled[0].status == "filled"
    assert filled[0].fill_price == 150.0


def test_evaluate_limit_order_buy_hit(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="limit",
        quantity=10.0,
        limit_price=150.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    dates = pd.DatetimeIndex(["2025-01-02"])
    df = pd.DataFrame(
        {
            "Open": [152.0],
            "High": [153.0],
            "Low": [149.0],
            "Close": [150.5],
        },
        index=dates,
    )
    bar = df.iloc[0]

    filled = env["manager"].evaluate(bar, [placed])
    assert len(filled) == 1
    assert filled[0].status == "filled"
    assert filled[0].fill_price == 150.0


def test_evaluate_limit_order_buy_miss(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="limit",
        quantity=10.0,
        limit_price=150.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    dates = pd.DatetimeIndex(["2025-01-02"])
    df = pd.DataFrame(
        {
            "Open": [152.0],
            "High": [153.0],
            "Low": [151.0],
            "Close": [150.5],
        },
        index=dates,
    )
    bar = df.iloc[0]

    filled = env["manager"].evaluate(bar, [placed])
    assert len(filled) == 0


def test_evaluate_limit_order_short_hit(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="short",
        order_type="limit",
        quantity=10.0,
        limit_price=150.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    dates = pd.DatetimeIndex(["2025-01-02"])
    df = pd.DataFrame(
        {
            "Open": [148.0],
            "High": [150.0],
            "Low": [147.0],
            "Close": [150.5],
        },
        index=dates,
    )
    bar = df.iloc[0]

    filled = env["manager"].evaluate(bar, [placed])
    assert len(filled) == 1
    assert filled[0].status == "filled"
    assert filled[0].fill_price == 150.0


def test_expire_orders(setup_trading_env):
    from phantom.utils.datetime import parse_datetime

    env = setup_trading_env
    past_time = parse_datetime("2025-01-01T12:00:00Z")
    future_time = parse_datetime("2025-12-31T12:00:00Z")
    current_time = parse_datetime("2025-06-15T12:00:00Z")

    order_expired = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=10.0,
        good_til=past_time,
    )
    order_active = Order(
        account_id=env["account"].id,
        ticker="GOOGL",
        instrument_type="stock",
        direction="short",
        order_type="market",
        quantity=5.0,
        good_til=future_time,
    )

    active, expired = env["manager"].expire_orders([order_expired, order_active], current_time)
    assert len(active) == 1
    assert len(expired) == 1
    assert active[0].ticker == "GOOGL"
    assert expired[0].ticker == "AAPL"
    assert expired[0].status == "expired"
