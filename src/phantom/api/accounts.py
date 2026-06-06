import sqlite3

from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.errors import NotFoundError, ValidationError
from phantom.models.account import Account
from phantom.models.types import AccountType


class AccountAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._repo = AccountRepo(conn)
        self._broker_repo = BrokerRepo(conn)

    def create(
        self,
        name: str,
        account_type: AccountType,
        broker: str,
        capital: float,
        currency: str = "EUR",
        pattern_tag: str | None = None,
        algorithm_id: str | None = None,
        algorithm_version: str | None = None,
        algorithm_params: dict | None = None,
        child_account_ids: list[str] | None = None,
    ) -> Account:
        self._broker_repo.get_by_name(broker)
        broker_id = self._broker_repo.get_id_by_name(broker)
        if account_type == "pattern" and not pattern_tag:
            raise ValidationError("pattern_tag is required for pattern accounts")
        if account_type == "algorithm" and not algorithm_id:
            raise ValidationError("algorithm_id is required for algorithm accounts")
        account = Account(
            name=name,
            account_type=account_type,
            broker_profile_id=broker_id,
            base_currency=currency,
            initial_capital=capital,
            cash=capital,
            pattern_tag=pattern_tag,
            algorithm_id=algorithm_id,
            algorithm_version=algorithm_version,
            algorithm_params=algorithm_params,
            child_account_ids=child_account_ids,
        )
        return self._repo.create(account)

    def list(self, account_type: str | None = None) -> list[Account]:
        return self._repo.list(account_type=account_type)

    def get(self, id_or_name: str) -> Account:
        try:
            return self._repo.get(id_or_name)
        except NotFoundError:
            return self._repo.get_by_name(id_or_name)

    def delete(self, account_id: str) -> None:
        self._repo.delete(account_id)
