from datetime import datetime
import sqlite3
from threading import Event

from phantom.costs.engine import CostEngine
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.replay_engine import ReplayEngine
from phantom.engine.simulation_engine import SimulationEngine
from phantom.models.backtest_result import BacktestResult
from phantom.models.position import Position


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

    def replay_position(self, position: Position) -> Position:
        account = self._account_repo.get(position.account_id)
        profile = self._broker_repo.get(account.broker_profile_id)
        cost_engine = CostEngine(profile)
        from phantom.config import get_data_dir
        from phantom.data.yahoo import HistoricalProvider

        data_provider = HistoricalProvider(get_data_dir())
        position_repo = PositionRepo(self._conn)
        engine = ReplayEngine(data_provider, cost_engine, position_repo)
        return engine.replay_position(position)

    def paper_trade(
        self,
        account_id: str,
        tickers: list[str],
        interval: float = 300.0,
        stop_event: Event | None = None,
        data_provider=None,
    ) -> None:
        """Run paper trading loop.

        Args:
            account_id: Account ID to trade
            tickers: List of tickers to fetch bars for
            interval: Interval in seconds between ticks (default: 300)
            stop_event: threading.Event to signal shutdown
            data_provider: Optional data provider (defaults to LiveProvider)
        """
        account = self._account_repo.get(account_id)
        profile = self._broker_repo.get(account.broker_profile_id)
        cost_engine = CostEngine(profile)

        if data_provider is None:
            from phantom.config import get_data_dir
            from phantom.data.alpaca import LiveProvider

            data_provider = LiveProvider(get_data_dir())

        engine = SimulationEngine(
            conn=self._conn,
            data_provider=data_provider,
            cost_engine=cost_engine,
        )

        engine.run_paper(
            account_id=account_id,
            tickers=tickers,
            interval=interval,
            stop_event=stop_event,
        )
