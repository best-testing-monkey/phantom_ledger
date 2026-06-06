import pytest

from phantom.db.repositories.account_repo import AccountRepo
from phantom.errors import NotFoundError
from phantom.models.account import Account
from phantom.utils.datetime import now_utc, to_iso
from phantom.utils.ids import new_id


@pytest.fixture
def broker_id(db_conn):
    """Create a broker profile for testing."""
    bid = new_id()
    db_conn.execute(
        "INSERT INTO broker_profiles"
        " (id, name, config_json, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (bid, "TEST_BROKER", "{}", to_iso(now_utc()), to_iso(now_utc())),
    )
    db_conn.commit()
    return bid


def test_account_repo_create_get(db_conn, broker_id):
    repo = AccountRepo(db_conn)
    account = Account(
        name="Test Account",
        account_type="manual",
        broker_profile_id=broker_id,
        initial_capital=10000.0,
        cash=10000.0,
    )
    repo.create(account)
    retrieved = repo.get(account.id)
    assert retrieved.name == "Test Account"
    assert retrieved.account_type == "manual"
    assert retrieved.initial_capital == 10000.0


def test_account_repo_get_by_name(db_conn, broker_id):
    repo = AccountRepo(db_conn)
    account = Account(
        name="Named Account",
        account_type="pattern",
        broker_profile_id=broker_id,
        initial_capital=5000.0,
        cash=5000.0,
        pattern_tag="test_pattern",
    )
    repo.create(account)
    retrieved = repo.get_by_name("Named Account")
    assert retrieved.id == account.id
    assert retrieved.pattern_tag == "test_pattern"


def test_account_repo_get_nonexistent(db_conn):
    repo = AccountRepo(db_conn)
    with pytest.raises(NotFoundError):
        repo.get("nonexistent_id")


def test_account_repo_get_by_name_nonexistent(db_conn):
    repo = AccountRepo(db_conn)
    with pytest.raises(NotFoundError):
        repo.get_by_name("nonexistent_name")


def test_account_repo_list_empty(db_conn):
    repo = AccountRepo(db_conn)
    accounts = repo.list()
    assert accounts == []


def test_account_repo_list_multiple(db_conn, broker_id):
    repo = AccountRepo(db_conn)
    for i in range(3):
        account = Account(
            name=f"Account {i}",
            account_type="manual",
            broker_profile_id=broker_id,
            initial_capital=1000.0 * (i + 1),
            cash=1000.0 * (i + 1),
        )
        repo.create(account)
    accounts = repo.list()
    assert len(accounts) == 3
    assert accounts[0].name == "Account 0"


def test_account_repo_list_by_type(db_conn, broker_id):
    repo = AccountRepo(db_conn)
    for atype in ["manual", "pattern", "manual"]:
        account = Account(
            name=f"Account {atype}",
            account_type=atype,
            broker_profile_id=broker_id,
            initial_capital=1000.0,
            cash=1000.0,
        )
        repo.create(account)
    manual_accounts = repo.list(account_type="manual")
    assert len(manual_accounts) == 2


def test_account_repo_update(db_conn, broker_id):
    repo = AccountRepo(db_conn)
    account = Account(
        name="Original",
        account_type="manual",
        broker_profile_id=broker_id,
        initial_capital=1000.0,
        cash=1000.0,
    )
    repo.create(account)
    account.name = "Updated"
    account.cash = 500.0
    repo.update(account)
    retrieved = repo.get(account.id)
    assert retrieved.name == "Updated"
    assert retrieved.cash == 500.0


def test_account_repo_update_nonexistent(db_conn, broker_id):
    repo = AccountRepo(db_conn)
    account = Account(
        id="nonexistent_id",
        name="Fake",
        account_type="manual",
        broker_profile_id=broker_id,
        initial_capital=1000.0,
        cash=1000.0,
    )
    with pytest.raises(NotFoundError):
        repo.update(account)


def test_account_repo_delete(db_conn, broker_id):
    repo = AccountRepo(db_conn)
    account = Account(
        name="To Delete",
        account_type="manual",
        broker_profile_id=broker_id,
        initial_capital=1000.0,
        cash=1000.0,
    )
    repo.create(account)
    repo.delete(account.id)
    with pytest.raises(NotFoundError):
        repo.get(account.id)


def test_account_repo_delete_nonexistent(db_conn):
    repo = AccountRepo(db_conn)
    with pytest.raises(NotFoundError):
        repo.delete("nonexistent_id")


def test_account_repo_algorithm_params_json(db_conn, broker_id):
    repo = AccountRepo(db_conn)
    params = {"param1": "value1", "param2": 42}
    account = Account(
        name="Algo Account",
        account_type="algorithm",
        broker_profile_id=broker_id,
        initial_capital=1000.0,
        cash=1000.0,
        algorithm_id="algo_1",
        algorithm_version="1.0",
        algorithm_params=params,
    )
    repo.create(account)
    retrieved = repo.get(account.id)
    assert retrieved.algorithm_params == params


def test_account_repo_child_account_ids_json(db_conn, broker_id):
    repo = AccountRepo(db_conn)
    child_ids = ["child_1", "child_2"]
    account = Account(
        name="Parent Account",
        account_type="aggregate",
        broker_profile_id=broker_id,
        initial_capital=1000.0,
        cash=1000.0,
        child_account_ids=child_ids,
    )
    repo.create(account)
    retrieved = repo.get(account.id)
    assert retrieved.child_account_ids == child_ids
