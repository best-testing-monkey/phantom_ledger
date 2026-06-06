import sqlite3

from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.models.broker import BrokerProfile
from phantom.profiles.loader import load_profile


class BrokerAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._repo = BrokerRepo(conn)

    def load(self, path: str) -> BrokerProfile:
        profile = load_profile(path)
        return self._repo.create(profile)

    def create_from_dict(self, data: dict) -> BrokerProfile:
        """Create a broker profile from a dictionary."""
        profile = BrokerProfile(**data)
        return self._repo.create(profile)

    def list(self) -> list[BrokerProfile]:
        return self._repo.list()

    def get(self, name: str) -> BrokerProfile:
        return self._repo.get_by_name(name)

    def validate(self, path: str) -> BrokerProfile:
        return load_profile(path)
