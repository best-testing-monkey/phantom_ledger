import pytest

from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.errors import NotFoundError


def test_broker_repo_create_get(db_conn, degiro_profile):
    repo = BrokerRepo(db_conn)
    repo.create(degiro_profile)
    retrieved = repo.get_by_name("DEGIRO_TEST")
    assert retrieved.name == "DEGIRO_TEST"
    assert retrieved.fx_conversion_pct == 0.0025


def test_broker_repo_get_nonexistent(db_conn):
    repo = BrokerRepo(db_conn)
    with pytest.raises(NotFoundError):
        repo.get_by_name("NONEXISTENT")


def test_broker_repo_list_empty(db_conn):
    repo = BrokerRepo(db_conn)
    profiles = repo.list()
    assert profiles == []


def test_broker_repo_list_multiple(db_conn, degiro_profile):
    repo = BrokerRepo(db_conn)
    repo.create(degiro_profile)
    profiles = repo.list()
    assert len(profiles) == 1
    assert profiles[0].name == "DEGIRO_TEST"


def test_broker_repo_delete(db_conn, degiro_profile):
    repo = BrokerRepo(db_conn)
    repo.create(degiro_profile)
    repo.delete("DEGIRO_TEST")
    with pytest.raises(NotFoundError):
        repo.get_by_name("DEGIRO_TEST")


def test_broker_repo_delete_nonexistent(db_conn):
    repo = BrokerRepo(db_conn)
    with pytest.raises(NotFoundError):
        repo.delete("NONEXISTENT")


def test_broker_repo_update(db_conn, degiro_profile):
    repo = BrokerRepo(db_conn)
    repo.create(degiro_profile)

    # Modify the profile and update it
    modified = degiro_profile.model_copy(update={"max_leverage": 99.0})
    repo.update(modified)

    # Verify the update persisted
    retrieved = repo.get_by_name("DEGIRO_TEST")
    assert retrieved.max_leverage == 99.0


def test_broker_repo_update_preserves_id(db_conn, degiro_profile):
    repo = BrokerRepo(db_conn)
    repo.create(degiro_profile)

    # Capture the ID before update
    id_before = repo.get_id_by_name("DEGIRO_TEST")

    # Modify and update the profile
    modified = degiro_profile.model_copy(update={"max_leverage": 50.0})
    repo.update(modified)

    # Verify the ID is unchanged
    id_after = repo.get_id_by_name("DEGIRO_TEST")
    assert id_before == id_after


def test_broker_repo_update_nonexistent(db_conn, degiro_profile):
    repo = BrokerRepo(db_conn)
    with pytest.raises(NotFoundError):
        repo.update(degiro_profile)
