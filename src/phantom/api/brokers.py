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

    def update(self, name: str, profile: BrokerProfile) -> BrokerProfile:
        """Update an already-loaded broker profile's config, preserving its id.

        Raises NotFoundError if no profile named `name` exists yet - this is
        not an upsert. If `profile.name` differs from `name`, the profile is
        renamed to `name` (the row is matched by `name`, so they must agree).
        """
        if profile.name != name:
            profile = profile.model_copy(update={"name": name})
        return self._repo.update(profile)
