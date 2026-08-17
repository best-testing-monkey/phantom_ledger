import pandas as pd
import pytest

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
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


@pytest.fixture
def setup_cfd_trading_env(db_conn):
    from phantom.utils.datetime import to_iso
    from phantom.utils.ids import new_id

    account_repo = AccountRepo(db_conn)
    order_repo = OrderRepo(db_conn)
    position_repo = PositionRepo(db_conn)
    broker_repo = BrokerRepo(db_conn)

    broker_id = new_id()
    # 10% margin => 10x leverage, CFDs supported.
    profile_json = (
        '{"name":"CFD_BROKER","commission":{"model_type":"fixed","fixed_fee":1.0},'
        '"spread":{"model_type":"fixed","fixed_spread_pct":0.0005},'
        '"slippage":{"model_type":"fixed_pct","fixed_pct":0.0003},'
        '"overnight":{"long_markup_pct":0.0,"short_markup_pct":0.0,'
        '"day_divisor":365,"rate_source":"manual","manual_rate":0.0},'
        '"margin":{"default_margin_pct":0.1,"margin_call_level":1.5,"stop_out_level":1.0,'
        '"classes":[{"label":"fx_majors","match":"^[A-Z]{3}(USD|EUR|GBP|JPY|CHF|AUD|CAD|NZD)$",'
        '"margin_pct":0.03}]},'
        '"dividend":{"withholding_rates":{"US":0.15},"cfd_dividend_adjustment":1.0,'
        '"cfd_short_dividend_charge":1.0},'
        '"fx_conversion_pct":0.0025,"fx_base_currency":"USD","min_order_size":1.0,'
        '"max_leverage":10.0,"trading_hours":{"timezone":"America/New_York",'
        '"open":"09:30","close":"16:00","pre_market":false,"post_market":false},'
        '"supported_instruments":["stock","cfd"]}'
    )
    db_conn.execute(
        """INSERT INTO broker_profiles
        (id, name, config_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)""",
        (broker_id, "CFD_BROKER", profile_json, to_iso(now_utc()), to_iso(now_utc())),
    )
    db_conn.commit()

    account = Account(
        name="cfd_account",
        account_type="manual",
        broker_profile_id=broker_id,
        base_currency="USD",
        initial_capital=10000.0,
        cash=10000.0,
    )
    account_repo.create(account)

    profile = BrokerProfile.model_validate_json(profile_json)
    cost_engine = CostEngine(profile)
    manager = OrderManager(order_repo, account_repo, cost_engine, broker_repo=broker_repo)

    return {
        "account": account,
        "manager": manager,
        "order_repo": order_repo,
        "position_repo": position_repo,
        "account_repo": account_repo,
    }


def test_handle_fill_cfd_deducts_margin_and_sets_leverage(setup_cfd_trading_env):
    env = setup_cfd_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="cfd",
        direction="long",
        order_type="market",
        quantity=10.0,
        fill_price=100.0,
        status="pending",
    )
    order = env["order_repo"].create(order)
    order = order.model_copy(update={"fill_price": 100.0, "filled_at": now_utc()})

    _, position = env["manager"].handle_fill(order, env["position_repo"])

    # notional = 1000, margin_pct = 0.1 => margin_required = 100, leverage = 10x
    assert position.notional == pytest.approx(1000.0)
    assert position.margin_required == pytest.approx(100.0)
    assert position.leverage == pytest.approx(10.0)

    account = env["account_repo"].get(env["account"].id)
    # Only margin + entry costs should have left the cash balance, not full notional.
    expected_cash = 10000.0 - 100.0 - (position.commission_entry + position.spread_cost)
    assert account.cash == pytest.approx(expected_cash, abs=1.0)
    assert account.cash > 8000.0  # sanity: nowhere near full $1000 notional debited


def test_handle_fill_cfd_uses_per_class_margin_rate(setup_cfd_trading_env):
    env = setup_cfd_trading_env

    fx_order = Order(
        account_id=env["account"].id,
        ticker="EURUSD",
        instrument_type="cfd",
        direction="long",
        order_type="market",
        quantity=10.0,
        fill_price=100.0,
        status="pending",
    )
    fx_order = env["order_repo"].create(fx_order)
    fx_order = fx_order.model_copy(update={"fill_price": 100.0, "filled_at": now_utc()})
    _, fx_position = env["manager"].handle_fill(fx_order, env["position_repo"])

    equity_order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="cfd",
        direction="long",
        order_type="market",
        quantity=10.0,
        fill_price=100.0,
        status="pending",
    )
    equity_order = env["order_repo"].create(equity_order)
    equity_order = equity_order.model_copy(update={"fill_price": 100.0, "filled_at": now_utc()})
    _, equity_position = env["manager"].handle_fill(equity_order, env["position_repo"])

    # EURUSD matches the fx_majors class => 3% margin => 30, 33.33x leverage.
    assert fx_position.margin_required == pytest.approx(30.0)
    assert fx_position.leverage == pytest.approx(1.0 / 0.03)

    # AAPL matches no class => falls back to default_margin_pct (10%) => 100, 10x leverage.
    assert equity_position.margin_required == pytest.approx(100.0)
    assert equity_position.leverage == pytest.approx(10.0)

    assert fx_position.margin_required != equity_position.margin_required
    assert fx_position.leverage != equity_position.leverage


def test_handle_fill_stock_still_deducts_full_notional(setup_cfd_trading_env):
    env = setup_cfd_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=10.0,
        fill_price=100.0,
        status="pending",
    )
    order = env["order_repo"].create(order)
    order = order.model_copy(update={"fill_price": 100.0, "filled_at": now_utc()})

    _, position = env["manager"].handle_fill(order, env["position_repo"])

    assert position.margin_required == 0.0
    assert position.leverage == 1.0
    account = env["account_repo"].get(env["account"].id)
    assert account.cash < 9001.0  # ~full $1000 notional + costs debited


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


def test_evaluate_stop_order_long(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="stop",
        quantity=10.0,
        stop_price=150.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    # Bar with high >= stop_price triggers
    dates = pd.DatetimeIndex(["2025-01-02"])
    df = pd.DataFrame(
        {
            "Open": [151.0],
            "High": [152.0],
            "Low": [148.0],
            "Close": [150.5],
        },
        index=dates,
    )
    bar = df.iloc[0]

    filled = env["manager"].evaluate(bar, [placed])
    assert len(filled) == 1
    assert filled[0].status == "filled"
    # Fill at max(stop_price, open) = max(150, 151) = 151
    assert filled[0].fill_price == 151.0


def test_evaluate_stop_order_long_gap_protection(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="stop",
        quantity=10.0,
        stop_price=150.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    # Gap up - open is below stop
    dates = pd.DatetimeIndex(["2025-01-02"])
    df = pd.DataFrame(
        {
            "Open": [148.0],
            "High": [152.0],
            "Low": [147.0],
            "Close": [150.5],
        },
        index=dates,
    )
    bar = df.iloc[0]

    filled = env["manager"].evaluate(bar, [placed])
    assert len(filled) == 1
    # Gap protection: fill at stop_price, not below
    assert filled[0].fill_price == 150.0


def test_evaluate_stop_order_short(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="short",
        order_type="stop",
        quantity=10.0,
        stop_price=150.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    # Bar with low <= stop_price triggers
    dates = pd.DatetimeIndex(["2025-01-02"])
    df = pd.DataFrame(
        {
            "Open": [149.0],
            "High": [152.0],
            "Low": [148.0],
            "Close": [150.5],
        },
        index=dates,
    )
    bar = df.iloc[0]

    filled = env["manager"].evaluate(bar, [placed])
    assert len(filled) == 1
    # Fill at min(stop_price, open) = min(150, 149) = 149
    assert filled[0].fill_price == 149.0


def test_evaluate_stop_limit_order_trigger_and_fill_same_bar(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="stop_limit",
        quantity=10.0,
        stop_price=150.0,
        limit_price=151.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    # Stop is triggered (high >= 150) and limit is fillable (low <= 151)
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
    assert filled[0].fill_price == 151.0


def test_evaluate_stop_limit_order_trigger_only(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="stop_limit",
        quantity=10.0,
        stop_price=150.0,
        limit_price=151.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    # Stop triggered (high >= 150) but limit not fillable (low > 151)
    dates = pd.DatetimeIndex(["2025-01-02"])
    df = pd.DataFrame(
        {
            "Open": [152.0],
            "High": [153.0],
            "Low": [152.0],
            "Close": [150.5],
        },
        index=dates,
    )
    bar = df.iloc[0]

    filled = env["manager"].evaluate(bar, [placed])
    assert len(filled) == 0
    # Order would be triggered but not filled - in reality would update DB


def test_evaluate_trailing_stop_long(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="trailing_stop",
        quantity=10.0,
        trailing_amount=5.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    # First bar - establishes peak
    dates1 = pd.DatetimeIndex(["2025-01-02"])
    df1 = pd.DataFrame(
        {
            "Open": [150.0],
            "High": [155.0],
            "Low": [149.0],
            "Close": [154.0],
        },
        index=dates1,
    )
    bar1 = df1.iloc[0]

    filled1 = env["manager"].evaluate(bar1, [placed])
    assert len(filled1) == 0  # Not triggered yet
    # Peak should be updated to 155

    # Second bar - peak moves higher
    updated_order = placed.model_copy(update={"trailing_peak": 155.0})
    dates2 = pd.DatetimeIndex(["2025-01-03"])
    df2 = pd.DataFrame(
        {
            "Open": [156.0],
            "High": [157.0],
            "Low": [154.0],
            "Close": [156.5],
        },
        index=dates2,
    )
    bar2 = df2.iloc[0]

    filled2 = env["manager"].evaluate(bar2, [updated_order])
    assert len(filled2) == 0  # Still not triggered

    # Third bar - price drops, triggers stop
    updated_order2 = updated_order.model_copy(update={"trailing_peak": 157.0})
    dates3 = pd.DatetimeIndex(["2025-01-04"])
    df3 = pd.DataFrame(
        {
            "Open": [150.0],
            "High": [152.0],
            "Low": [149.0],
            "Close": [151.0],
        },
        index=dates3,
    )
    bar3 = df3.iloc[0]

    filled3 = env["manager"].evaluate(bar3, [updated_order2])
    assert len(filled3) == 1
    # Trigger level = 157 - 5 = 152, fills at max(152, 150) = 152
    assert filled3[0].status == "filled"
    assert filled3[0].fill_price == 152.0


def test_evaluate_trailing_stop_short(setup_trading_env):
    env = setup_trading_env
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="short",
        order_type="trailing_stop",
        quantity=10.0,
        trailing_amount=5.0,
    )
    placed = env["manager"].place(env["account"].id, order)

    # First bar - establishes peak (min low)
    dates1 = pd.DatetimeIndex(["2025-01-02"])
    df1 = pd.DataFrame(
        {
            "Open": [150.0],
            "High": [155.0],
            "Low": [145.0],
            "Close": [146.0],
        },
        index=dates1,
    )
    bar1 = df1.iloc[0]

    filled1 = env["manager"].evaluate(bar1, [placed])
    assert len(filled1) == 0  # Not triggered yet
    # Peak should be updated to 145

    # Second bar - peak moves lower
    updated_order = placed.model_copy(update={"trailing_peak": 145.0})
    dates2 = pd.DatetimeIndex(["2025-01-03"])
    df2 = pd.DataFrame(
        {
            "Open": [144.0],
            "High": [147.0],
            "Low": [143.0],
            "Close": [144.5],
        },
        index=dates2,
    )
    bar2 = df2.iloc[0]

    filled2 = env["manager"].evaluate(bar2, [updated_order])
    assert len(filled2) == 0  # Still not triggered

    # Third bar - price rises, triggers stop
    updated_order2 = updated_order.model_copy(update={"trailing_peak": 143.0})
    dates3 = pd.DatetimeIndex(["2025-01-04"])
    df3 = pd.DataFrame(
        {
            "Open": [150.0],
            "High": [152.0],
            "Low": [149.0],
            "Close": [151.0],
        },
        index=dates3,
    )
    bar3 = df3.iloc[0]

    filled3 = env["manager"].evaluate(bar3, [updated_order2])
    assert len(filled3) == 1
    # Trigger level = 143 + 5 = 148, fills at min(148, 150) = 148
    assert filled3[0].status == "filled"
    assert filled3[0].fill_price == 148.0


def test_place_or_reject_insufficient_funds(setup_trading_env):
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

    rejected = env["manager"].place_or_reject(env["account"].id, order)
    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "insufficient_funds"


def test_handle_fill_or_reject_insufficient_funds(setup_trading_env):
    env = setup_trading_env
    # quantity * fill_price (200 * 100 = 20000) far exceeds the account's
    # 10000 cash, so the fill cannot be funded.
    order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=200.0,
        fill_price=100.0,
        status="pending",
    )
    order = env["order_repo"].create(order)
    order = order.model_copy(update={"fill_price": 100.0, "filled_at": now_utc()})

    orders_before = env["order_repo"].list_by_account(env["account"].id)
    assert len(orders_before) == 1

    rejected_order, position = env["manager"].handle_fill_or_reject(order, env["position_repo"])

    assert position is None
    assert rejected_order.status == "rejected"
    assert rejected_order.rejection_reason == "insufficient_funds"

    # The existing pending row was updated in place, not duplicated.
    refetched = env["order_repo"].get(order.id)
    assert refetched.status == "rejected"
    assert refetched.rejection_reason == "insufficient_funds"

    orders_after = env["order_repo"].list_by_account(env["account"].id)
    assert len(orders_after) == 1


def test_create_oco_pair(setup_trading_env):
    env = setup_trading_env
    tp_order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="limit",
        quantity=10.0,
        limit_price=160.0,  # Take profit at 160
    )
    sl_order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="stop",
        quantity=10.0,
        stop_price=140.0,  # Stop loss at 140
    )

    tp_placed, sl_placed = env["manager"].create_oco_pair(env["account"].id, tp_order, sl_order)

    assert tp_placed.oco_sibling_id == sl_placed.id
    assert sl_placed.oco_sibling_id == tp_placed.id
    assert tp_placed.status == "pending"
    assert sl_placed.status == "pending"


def test_oco_pair_fills_and_cancels_sibling(setup_trading_env):
    env = setup_trading_env
    tp_order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="limit",
        quantity=10.0,
        limit_price=160.0,
    )
    sl_order = Order(
        account_id=env["account"].id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="stop",
        quantity=10.0,
        stop_price=140.0,
    )

    tp_placed, sl_placed = env["manager"].create_oco_pair(env["account"].id, tp_order, sl_order)

    # TP hits (price goes to 161, low is 159)
    dates = pd.DatetimeIndex(["2025-01-02"])
    df = pd.DataFrame(
        {
            "Open": [161.0],
            "High": [162.0],
            "Low": [159.0],
            "Close": [161.5],
        },
        index=dates,
    )
    bar = df.iloc[0]

    filled = env["manager"].evaluate(bar, [tp_placed])
    assert len(filled) == 1
    assert filled[0].status == "filled"

    # Handle fill (cancel sibling)
    env["manager"].handle_oco_fill(filled[0])

    # Verify sibling is cancelled
    sl_cancelled = env["order_repo"].get(sl_placed.id)
    assert sl_cancelled.status == "cancelled"
