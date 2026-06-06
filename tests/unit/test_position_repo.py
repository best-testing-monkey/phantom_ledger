import pytest

from phantom.db.repositories.position_repo import PositionRepo
from phantom.errors import NotFoundError
from phantom.models.position import Position
from phantom.utils.datetime import now_utc, to_iso
from phantom.utils.ids import new_id


@pytest.fixture
def position_repo(db_conn):
    return PositionRepo(db_conn)


def _setup_account(conn):
    bid = new_id()
    conn.execute(
        "INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (bid, "TEST", "{}", to_iso(now_utc()), to_iso(now_utc())),
    )
    aid = new_id()
    conn.execute(
        "INSERT INTO accounts (id, name, account_type, broker_profile_id, base_currency, initial_capital, cash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, "acct", "manual", bid, "EUR", 10000.0, 10000.0, to_iso(now_utc())),
    )
    oid = new_id()
    conn.execute(
        "INSERT INTO orders (id, account_id, ticker, instrument_type, direction, order_type, quantity, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (oid, aid, "AAPL", "stock", "long", "market", 10.0, "filled", to_iso(now_utc())),
    )
    conn.commit()
    return aid, oid


def test_create_and_get(position_repo, db_conn):
    aid, oid = _setup_account(db_conn)
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
    )
    created = position_repo.create(pos)
    assert created.id == pos.id
    assert created.ticker == "AAPL"

    retrieved = position_repo.get(pos.id)
    assert retrieved.id == pos.id
    assert retrieved.account_id == aid
    assert retrieved.ticker == "AAPL"


def test_get_nonexistent_raises_not_found(position_repo):
    with pytest.raises(NotFoundError) as exc_info:
        position_repo.get("nonexistent")
    assert "Position" in str(exc_info.value)


def test_list_by_account_empty(position_repo, db_conn):
    aid, _ = _setup_account(db_conn)
    positions = position_repo.list_by_account(aid)
    assert positions == []


def test_list_by_account_with_positions(position_repo, db_conn):
    aid, oid = _setup_account(db_conn)
    pos1 = Position(
        account_id=aid,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
    )
    pos2 = Position(
        account_id=aid,
        ticker="GOOGL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=2800.0,
        entry_datetime=now_utc(),
        quantity=1.0,
        notional=2800.0,
    )
    position_repo.create(pos1)
    position_repo.create(pos2)

    positions = position_repo.list_by_account(aid)
    assert len(positions) == 2
    assert any(p.ticker == "AAPL" for p in positions)
    assert any(p.ticker == "GOOGL" for p in positions)


def test_list_by_account_with_status_filter(position_repo, db_conn):
    aid, oid = _setup_account(db_conn)
    pos1 = Position(
        account_id=aid,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        status="open",
    )
    pos2 = Position(
        account_id=aid,
        ticker="GOOGL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=2800.0,
        entry_datetime=now_utc(),
        quantity=1.0,
        notional=2800.0,
        status="closed",
    )
    position_repo.create(pos1)
    position_repo.create(pos2)

    open_positions = position_repo.list_by_account(aid, status="open")
    assert len(open_positions) == 1
    assert open_positions[0].ticker == "AAPL"

    closed_positions = position_repo.list_by_account(aid, status="closed")
    assert len(closed_positions) == 1
    assert closed_positions[0].ticker == "GOOGL"


def test_list_by_account_with_ticker_filter(position_repo, db_conn):
    aid, oid = _setup_account(db_conn)
    pos1 = Position(
        account_id=aid,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
    )
    pos2 = Position(
        account_id=aid,
        ticker="GOOGL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=2800.0,
        entry_datetime=now_utc(),
        quantity=1.0,
        notional=2800.0,
    )
    position_repo.create(pos1)
    position_repo.create(pos2)

    aapl_positions = position_repo.list_by_account(aid, ticker="AAPL")
    assert len(aapl_positions) == 1
    assert aapl_positions[0].ticker == "AAPL"


def test_list_open(position_repo, db_conn):
    aid, oid = _setup_account(db_conn)
    pos1 = Position(
        account_id=aid,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=150.0,
        entry_datetime=now_utc(),
        quantity=10.0,
        notional=1500.0,
        status="open",
    )
    pos2 = Position(
        account_id=aid,
        ticker="GOOGL",
        instrument_type="stock",
        direction="long",
        entry_order_id=oid,
        entry_price=2800.0,
        entry_datetime=now_utc(),
        quantity=1.0,
        notional=2800.0,
        status="closed",
    )
    position_repo.create(pos1)
    position_repo.create(pos2)

    open_positions = position_repo.list_open()
    assert len(open_positions) == 1
    assert open_positions[0].ticker == "AAPL"


def test_update(position_repo, db_conn):
    aid, oid = _setup_account(db_conn)
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

    pos_updated = pos.model_copy(
        update={
            "take_profit": 165.0,
            "stop_loss": 135.0,
        }
    )
    updated = position_repo.update(pos_updated)
    assert updated.take_profit == 165.0
    assert updated.stop_loss == 135.0

    retrieved = position_repo.get(pos.id)
    assert retrieved.take_profit == 165.0
    assert retrieved.stop_loss == 135.0
