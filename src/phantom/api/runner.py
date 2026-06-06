from datetime import datetime
import sqlite3

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.engine.simulation_engine import SimulationEngine
from phantom.models.backtest_result import BacktestResult


class RunnerAPI:
    def __init__(self, conn: sqlite3.Connection, broker_repo: BrokerRepo):
        self._conn = conn
        self._broker_repo = broker_repo
        self._account_repo = AccountRepo(conn)

    def backtest(
        self,
        account_id: str,
        tickers: list[str],
        start: str | datetime,
        end: str | datetime,
        data_provider=None,
    ) -> BacktestResult:
        account = self._account_repo.get(account_id)
        profile = self._broker_repo.get(account.broker_profile_id)
        cost_engine = CostEngine(profile)
        if data_provider is None:
            from phantom.config import get_data_dir
            from phantom.data.yahoo import HistoricalProvider

            data_provider = HistoricalProvider(get_data_dir())
        engine = SimulationEngine(
            conn=self._conn,
            data_provider=data_provider,
            cost_engine=cost_engine,
        )
        return engine.run_backtest(account_id=account_id, tickers=tickers, start=start, end=end)

    def replay(self, account_id: str) -> None:
        raise NotImplementedError

    def replay_position(self, position_id: str) -> None:
        raise NotImplementedError
