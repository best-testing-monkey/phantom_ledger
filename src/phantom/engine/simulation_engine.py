from datetime import datetime
import logging
import sqlite3

from phantom.costs.engine import CostEngine
from phantom.data.provider import DataProvider
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.equity_repo import EquityRepo
from phantom.db.repositories.order_repo import OrderRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.clock import BacktestClock
from phantom.engine.order_manager import OrderManager
from phantom.engine.position_manager import PositionManager
from phantom.models.backtest_result import BacktestResult
from phantom.models.equity_point import EquityPoint
from phantom.utils.datetime import parse_datetime, to_iso

logger = logging.getLogger(__name__)


class SimulationEngine:
    def __init__(
        self,
        conn: sqlite3.Connection,
        data_provider: DataProvider,
        cost_engine: CostEngine,
    ):
        self._conn = conn
        self._data_provider = data_provider
        self._cost_engine = cost_engine
        self._account_repo = AccountRepo(conn)
        self._order_repo = OrderRepo(conn)
        self._position_repo = PositionRepo(conn)
        self._equity_repo = EquityRepo(conn)
        self._order_manager = OrderManager(
            order_repo=self._order_repo,
            account_repo=self._account_repo,
            cost_engine=cost_engine,
        )
        self._position_manager = PositionManager(
            position_repo=self._position_repo,
            account_repo=self._account_repo,
            cost_engine=cost_engine,
        )

    def run_backtest(
        self,
        account_id: str,
        tickers: list[str],
        start: str | datetime,
        end: str | datetime,
    ) -> BacktestResult:
        if isinstance(start, str):
            start = parse_datetime(start)
        if isinstance(end, str):
            end = parse_datetime(end)

        ticker = tickers[0] if tickers else ""
        price_data = self._data_provider.get_bars(ticker, start, end)
        if price_data.empty:
            account = self._account_repo.get(account_id)
            return BacktestResult(account=account)

        clock = BacktestClock(price_data.index)
        filled_orders: list = []
        closed_positions: list = []

        while not clock.is_done():
            current_time = clock.now()
            bar = price_data.loc[price_data.index[clock._pos]]

            pending = self._order_repo.list_by_account(account_id, status="pending")
            active, expired = self._order_manager.expire_orders(pending, current_time)

            for exp_order in expired:
                self._order_repo.update_status(exp_order.id, "expired")

            new_fills = self._order_manager.evaluate(bar, active)
            for filled_order in new_fills:
                filled_order_obj, position = self._order_manager.handle_fill(
                    filled_order, self._position_repo
                )
                filled_orders.append(filled_order_obj)
                logger.info(
                    "Order %s filled at %.2f", filled_order_obj.id, filled_order_obj.fill_price
                )

            open_positions = self._position_repo.list_by_account(account_id, status="open")
            for position in open_positions:
                result = self._position_manager.determine_close(position, bar)
                if result is not None:
                    exit_price, close_reason = result
                    bar_ts = current_time
                    closed = self._position_manager.close(
                        position, exit_price, close_reason, bar_ts
                    )
                    self._position_repo.update(closed)
                    acct = self._account_repo.get(account_id)
                    exit_costs = self._cost_engine.exit_costs(
                        price=exit_price,
                        quantity=position.quantity,
                        ticker=position.ticker,
                        instrument_type=position.instrument_type,
                    )
                    cash_return = exit_price * position.quantity - exit_costs.total
                    acct = acct.model_copy(update={"cash": acct.cash + cash_return})
                    self._account_repo.update(acct)
                    closed_positions.append(self._position_repo.get(position.id))

            open_positions = self._position_repo.list_by_account(account_id, status="open")
            account = self._account_repo.get(account_id)
            market_value = sum(p.quantity * float(bar["Close"]) for p in open_positions)
            unrealized = sum(
                (float(bar["Close"]) - p.entry_price) * p.quantity
                if p.direction == "long"
                else (p.entry_price - float(bar["Close"])) * p.quantity
                for p in open_positions
            )
            equity = account.cash + market_value
            point = EquityPoint(
                account_id=account_id,
                timestamp=to_iso(current_time),
                equity=equity,
                cash=account.cash,
                unrealized_pnl=unrealized,
            )
            self._equity_repo.create(point)

            clock.advance()

        account = self._account_repo.get(account_id)
        equity_curve = self._equity_repo.list(account_id)
        return BacktestResult(
            account=account,
            equity_curve=equity_curve,
            filled_orders=filled_orders,
            closed_positions=closed_positions,
        )
