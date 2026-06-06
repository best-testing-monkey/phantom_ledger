import sqlite3

from phantom.errors import NotFoundError
from phantom.models.broker import BrokerProfile
from phantom.utils.datetime import now_utc, to_iso
from phantom.utils.ids import new_id


class BrokerRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, profile: BrokerProfile) -> BrokerProfile:
        self._conn.execute(
            "INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                new_id(),
                profile.name,
                profile.model_dump_json(),
                to_iso(now_utc()),
                to_iso(now_utc()),
            ),
        )
        self._conn.commit()
        return profile

    def get_id_by_name(self, name: str) -> str:
        row = self._conn.execute(
            "SELECT id FROM broker_profiles WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise NotFoundError("BrokerProfile", name)
        return row["id"]

    def get(self, profile_id: str) -> BrokerProfile:
        row = self._conn.execute(
            "SELECT config_json FROM broker_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("BrokerProfile", profile_id)
        return BrokerProfile.model_validate_json(row["config_json"])

    def get_by_name(self, name: str) -> BrokerProfile:
        row = self._conn.execute(
            "SELECT config_json FROM broker_profiles WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise NotFoundError("BrokerProfile", name)
        return BrokerProfile.model_validate_json(row["config_json"])

    def list(self) -> list[BrokerProfile]:
        rows = self._conn.execute(
            "SELECT config_json FROM broker_profiles ORDER BY name"
        ).fetchall()
        return [BrokerProfile.model_validate_json(r["config_json"]) for r in rows]

    def delete(self, name: str) -> None:
        cursor = self._conn.execute("DELETE FROM broker_profiles WHERE name = ?", (name,))
        if cursor.rowcount == 0:
            raise NotFoundError("BrokerProfile", name)
        self._conn.commit()
