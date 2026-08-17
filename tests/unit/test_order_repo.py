import pytest

from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.order_repo import OrderRepo
from phantom.errors import NotFoundError
from phantom.models.account import Account
from phantom.models.order import Order
from phantom.utils.datetime import now_utc, to_iso


@pytest.fixture
def setup_test_data(db_conn):
    from phantom.utils.ids import new_id

    # Insert broker profile directly with a known ID
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

    account_repo = AccountRepo(db_conn)
    account = Account(
        name="test_account",
        account_type="manual",
        broker_profile_id=broker_id,
        base_currency="USD",
        initial_capital=10000.0,
        cash=10000.0,
    )
    account_repo.create(account)

    return db_conn, account


def test_order_create_and_get(setup_test_data):
    db_conn, account = setup_test_data
    order_repo = OrderRepo(db_conn)

    order = Order(
        account_id=account.id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="limit",
        quantity=10.0,
        limit_price=150.0,
    )
    created = order_repo.create(order)

    retrieved = order_repo.get(created.id)
    assert retrieved.id == created.id
    assert retrieved.ticker == "AAPL"
    assert retrieved.status == "pending"


def test_get_nonexistent_raises_notfound(setup_test_data):
    db_conn, _ = setup_test_data
    order_repo = OrderRepo(db_conn)

    with pytest.raises(NotFoundError) as exc_info:
        order_repo.get("nonexistent_id")
    assert "Order not found" in str(exc_info.value)


def test_update_status(setup_test_data):
    db_conn, account = setup_test_data
    order_repo = OrderRepo(db_conn)

    order = Order(
        account_id=account.id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=10.0,
    )
    created = order_repo.create(order)

    updated = order_repo.update_status(created.id, "filled", fill_price=150.0)
    assert updated.status == "filled"
    assert updated.fill_price == 150.0


def test_list_by_account(setup_test_data):
    db_conn, account = setup_test_data
    order_repo = OrderRepo(db_conn)

    order1 = Order(
        account_id=account.id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=10.0,
    )
    order2 = Order(
        account_id=account.id,
        ticker="GOOGL",
        instrument_type="stock",
        direction="short",
        order_type="limit",
        quantity=5.0,
        limit_price=100.0,
    )
    order_repo.create(order1)
    order_repo.create(order2)

    orders = order_repo.list_by_account(account.id)
    assert len(orders) == 2
    assert orders[0].ticker == "AAPL"
    assert orders[1].ticker == "GOOGL"


def test_list_by_account_with_status(setup_test_data):
    db_conn, account = setup_test_data
    order_repo = OrderRepo(db_conn)

    order1 = Order(
        account_id=account.id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=10.0,
        status="pending",
    )
    order2 = Order(
        account_id=account.id,
        ticker="GOOGL",
        instrument_type="stock",
        direction="short",
        order_type="limit",
        quantity=5.0,
        limit_price=100.0,
        status="filled",
    )
    order_repo.create(order1)
    order_repo.create(order2)

    pending_orders = order_repo.list_by_account(account.id, status="pending")
    assert len(pending_orders) == 1
    assert pending_orders[0].ticker == "AAPL"


def test_list_pending(setup_test_data):
    db_conn, account = setup_test_data
    order_repo = OrderRepo(db_conn)

    order1 = Order(
        account_id=account.id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=10.0,
    )
    order2 = Order(
        account_id=account.id,
        ticker="GOOGL",
        instrument_type="stock",
        direction="short",
        order_type="market",
        quantity=5.0,
        status="filled",
    )
    order_repo.create(order1)
    order_repo.create(order2)

    pending = order_repo.list_pending()
    assert len(pending) == 1
    assert pending[0].ticker == "AAPL"


def test_list_empty(setup_test_data):
    db_conn, account = setup_test_data
    order_repo = OrderRepo(db_conn)

    orders = order_repo.list_by_account(account.id)
    assert orders == []


def test_update_prices(setup_test_data):
    db_conn, account = setup_test_data
    order_repo = OrderRepo(db_conn)

    order = Order(
        account_id=account.id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="limit",
        quantity=10.0,
        limit_price=150.0,
    )
    created = order_repo.create(order)

    updated = order_repo.update_prices(created.id, {"limit_price": 155.0, "stop_loss": 140.0})
    assert updated.limit_price == 155.0
    assert updated.stop_loss == 140.0
