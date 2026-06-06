from pathlib import Path

from phantom.api.accounts import AccountAPI
from phantom.api.brokers import BrokerAPI
from phantom.api.data_api import DataAPI
from phantom.api.notes import NoteAPI
from phantom.api.orders import OrderAPI
from phantom.api.positions import PositionAPI
from phantom.api.reports import ReportAPI
from phantom.api.runner import RunnerAPI
from phantom.config import ensure_dirs
from phantom.db.database import get_connection, run_migrations
from phantom.db.repositories.broker_repo import BrokerRepo


class Phantom:
    def __init__(self, data_dir: str, in_memory: bool = False):
        ensure_dirs(data_dir)
        db_path = ":memory:" if in_memory else Path(data_dir) / "phantom.db"
        self._conn = get_connection(db_path)
        run_migrations(self._conn)

        broker_repo = BrokerRepo(self._conn)

        self.accounts = AccountAPI(self._conn)
        self.orders = OrderAPI(self._conn, broker_repo)
        self.positions = PositionAPI(self._conn, broker_repo)
        self.notes = NoteAPI(self._conn)
        self.data = DataAPI(self._conn, data_dir=data_dir)
        self.brokers = BrokerAPI(self._conn)
        self.reports = ReportAPI(self._conn)
        self.runner = RunnerAPI(self._conn)
