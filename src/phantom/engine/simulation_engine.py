from datetime import datetime, timezone
import logging
import signal
import sqlite3
from threading import Event

from phantom.costs.engine import CostEngine
from phantom.data.provider import DataProvider
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.dividend_log_repo import DividendLogRepo
from phantom.db.repositories.equity_repo import EquityRepo
from phantom.db.repositories.order_repo import OrderRepo
from phantom.db.repositories.overnight_log_repo import OvernightLogRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.engine.clock import BacktestClock, LiveClock
from phantom.engine.margin_engine import MarginEngine
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
        self._overnight_log_repo = OvernightLogRepo(conn)
        self._dividend_log_repo = DividendLogRepo(conn)
        self._margin_engine = MarginEngine()
        self._order_manager = OrderManager(
            order_repo=self._order_repo,
            account_repo=self._account_repo,
            cost_engine=cost_engine,
        )
        self._position_manager = PositionManager(
            position_repo=self._position_repo,
            account_repo=self._account_repo,
            cost_engine=cost_engine,
            overnight_log_repo=self._overnight_log_repo,
            dividend_log_repo=self._dividend_log_repo,
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

    def _apply_overnight_costs(
        self,
        account,
        open_positions: list,
        prev_bar_date: str,
        current_bar_date: str,
        broker_profile,
    ) -> None:
        """Apply overnight financing charges to CFD positions on day boundary.

        Args:
            account: Account to update
            open_positions: List of open positions
            prev_bar_date: Previous bar's date (YYYY-MM-DD)
            current_bar_date: Current bar's date (YYYY-MM-DD)
            broker_profile: BrokerProfile with overnight model and rate source
        """
        if prev_bar_date == current_bar_date:
            return

        for position in open_positions:
            if position.instrument_type != "cfd":
                continue

            # Fetch reference rate
            reference_rate = 0.0
            try:
                if broker_profile.overnight.rate_source == "manual":
                    reference_rate = broker_profile.overnight.manual_rate
                else:
                    # Try to fetch from rate provider
                    from phantom.data.rates import get_reference_rate

                    reference_rate = get_reference_rate(
                        broker_profile.overnight.rate_source,
                        current_bar_date,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to fetch reference rate for %s: %s",
                    broker_profile.overnight.rate_source,
                    e,
                )
                reference_rate = 0.0

            charge = self._cost_engine.overnight_cost(
                notional=position.notional,
                direction=position.direction,
                reference_rate=reference_rate,
            )

            if charge > 0:
                position.overnight_accrued += charge
                account.cash -= charge
                self._account_repo.update(account)
                self._position_repo.update(position)

                logger.debug(
                    "Applied overnight cost %s to position %s",
                    charge,
                    position.id,
                )

    def _apply_dividends(
        self,
        account,
        open_positions: list,
        bar_date: str,
        broker_profile,
    ) -> None:
        """Apply dividend adjustments to positions on ex-date.

        Args:
            account: Account to update
            open_positions: List of open positions
            bar_date: Current bar date (YYYY-MM-DD)
            broker_profile: BrokerProfile with dividend model
        """
        for position in open_positions:
            try:
                dividend_event = self._data_provider.get_dividends(
                    position.ticker,
                    parse_datetime(bar_date),
                    parse_datetime(bar_date),
                )
                if not dividend_event:
                    continue

                div = dividend_event[0]
                gross = div.amount * position.quantity

                if position.instrument_type == "stock":
                    withholding_rate = broker_profile.dividend.withholding_rates.get(
                        getattr(position, "country_code", "US"), 0.15
                    )
                    adjustment = gross * (1 - withholding_rate)
                elif position.direction == "long":
                    adjustment = gross * broker_profile.dividend.cfd_dividend_adjustment
                else:
                    adjustment = -(gross * broker_profile.dividend.cfd_short_dividend_charge)

                if adjustment != 0:
                    position.dividend_adjustments += adjustment
                    account.cash += adjustment
                    self._account_repo.update(account)
                    self._position_repo.update(position)

                    logger.debug(
                        "Applied dividend adjustment %s to position %s",
                        adjustment,
                        position.id,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to process dividend for %s: %s",
                    position.ticker,
                    e,
                )

    def _check_margin(
        self,
        account,
        open_positions: list,
        broker_profile,
        current_bar,
    ) -> list:
        """Check margin status and handle margin calls / stop-outs.

        Args:
            account: Account to check
            open_positions: List of open positions
            broker_profile: BrokerProfile with margin settings
            current_bar: Current price bar

        Returns:
            Updated list of open positions (after any forced closes)
        """
        if not open_positions:
            return open_positions

        # Only check if account has CFD positions
        has_cfd = any(p.instrument_type == "cfd" for p in open_positions)
        if not has_cfd:
            return open_positions

        # Calculate market value
        if hasattr(current_bar, "name"):
            current_time = current_bar.name
            if hasattr(current_time, "to_pydatetime"):
                current_time = current_time.to_pydatetime()
        else:
            current_time = datetime.now(timezone.utc)

        close_price = float(current_bar.get("Close", 0.0))
        open_position_market_value = sum(p.notional for p in open_positions)

        margin_status = self._margin_engine.check(
            account, broker_profile, open_position_market_value
        )

        if margin_status.status == "stop_out":
            closed = self._margin_engine.handle_stop_out(
                account=account,
                open_positions=open_positions,
                broker_profile=broker_profile,
                current_bar_timestamp=current_time,
                position_manager=self._position_manager,
                account_repo=self._account_repo,
            )

            # Deduct exit costs and update account cash
            for closed_pos in closed:
                exit_costs = self._cost_engine.exit_costs(
                    price=close_price,
                    quantity=closed_pos.quantity,
                    ticker=closed_pos.ticker,
                    instrument_type=closed_pos.instrument_type,
                )
                account.cash -= exit_costs.total
                self._position_repo.update(closed_pos)

            self._account_repo.update(account)

            # Remove closed positions from open list
            remaining = [p for p in open_positions if p.id not in [cp.id for cp in closed]]
            return remaining

        elif margin_status.status == "margin_call":
            self._margin_engine.handle_margin_call(account, margin_status, self._account_repo)

        return open_positions

    def run_paper(
        self,
        account_id: str,
        tickers: list[str],
        interval: float,
        stop_event: Event | None = None,
    ) -> None:
        """Run paper trading loop until stop_event is set.

        Fetches live bars, evaluates orders, updates positions, applies
        overnight costs, dividends, and margin checks. Commits state after
        each tick.

        Args:
            account_id: Account ID to trade
            tickers: List of tickers to fetch bars for
            interval: Interval in seconds between ticks
            stop_event: threading.Event to signal graceful shutdown
        """
        if stop_event is None:
            stop_event = Event()

        account = self._account_repo.get(account_id)
        profile = self._account_repo._conn.execute(
            "SELECT config_json FROM broker_profiles WHERE id = ?",
            (account.broker_profile_id,),
        ).fetchone()

        if profile is None:
            raise ValueError(f"Broker profile not found: {account.broker_profile_id}")

        from phantom.models.broker import BrokerProfile

        broker_profile = BrokerProfile.model_validate_json(profile[0])

        clock = LiveClock(interval)

        # Register signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info("Received signal %s, shutting down...", signum)
            stop_event.set()

        old_sigint = signal.signal(signal.SIGINT, signal_handler)
        old_sigterm = signal.signal(signal.SIGTERM, signal_handler)

        prev_bar_date = None

        try:
            while not stop_event.is_set():
                current_time = clock.now()
                current_time_str = to_iso(current_time)
                bar_date = current_time_str.split("T")[0]

                ticker = tickers[0] if tickers else None
                if not ticker:
                    logger.warning("No tickers specified for paper trading")
                    break

                try:
                    # Fetch current bar
                    bar_data = self._data_provider.get_bars(
                        ticker,
                        parse_datetime(bar_date),
                        parse_datetime(bar_date),
                    )

                    if bar_data.empty:
                        logger.debug("No bars available for %s on %s", ticker, bar_date)
                        clock.advance()
                        continue

                    bar = bar_data.iloc[-1]

                    # Evaluate pending orders
                    pending = self._order_repo.list_by_account(account_id, status="pending")
                    active, expired = self._order_manager.expire_orders(pending, current_time)

                    for exp_order in expired:
                        self._order_repo.update_status(exp_order.id, "expired")
                        logger.info("Order %s expired", exp_order.id)

                    new_fills = self._order_manager.evaluate(bar, active)
                    for filled_order in new_fills:
                        filled_order_obj, position = self._order_manager.handle_fill(
                            filled_order, self._position_repo
                        )
                        logger.info(
                            "Order %s filled at %.2f",
                            filled_order_obj.id,
                            filled_order_obj.fill_price,
                        )

                    # Reload account and positions
                    account = self._account_repo.get(account_id)
                    open_positions = self._position_repo.list_by_account(account_id, status="open")

                    # Apply overnight costs (on day boundary)
                    if prev_bar_date and prev_bar_date != bar_date:
                        self._apply_overnight_costs(
                            account,
                            open_positions,
                            prev_bar_date,
                            bar_date,
                            broker_profile,
                        )
                        account = self._account_repo.get(account_id)
                        open_positions = self._position_repo.list_by_account(
                            account_id, status="open"
                        )

                    # Apply dividends
                    self._apply_dividends(account, open_positions, bar_date, broker_profile)
                    account = self._account_repo.get(account_id)
                    open_positions = self._position_repo.list_by_account(account_id, status="open")

                    # Update positions and check TP/SL
                    for position in open_positions:
                        result = self._position_manager.determine_close(position, bar)
                        if result is not None:
                            exit_price, close_reason = result
                            closed = self._position_manager.close(
                                position, exit_price, close_reason, current_time
                            )
                            self._position_repo.update(closed)

                            exit_costs = self._cost_engine.exit_costs(
                                price=exit_price,
                                quantity=position.quantity,
                                ticker=position.ticker,
                                instrument_type=position.instrument_type,
                            )
                            cash_return = exit_price * position.quantity - exit_costs.total
                            account.cash += cash_return
                            logger.info(
                                "Position %s closed: %s at %.2f",
                                position.id,
                                close_reason,
                                exit_price,
                            )

                    # Check margin and handle stop-outs
                    open_positions = self._position_repo.list_by_account(account_id, status="open")
                    account = self._account_repo.get(account_id)
                    open_positions = self._check_margin(
                        account, open_positions, broker_profile, bar
                    )

                    # Record equity point
                    account = self._account_repo.get(account_id)
                    open_positions = self._position_repo.list_by_account(account_id, status="open")
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
                        timestamp=current_time_str,
                        equity=equity,
                        cash=account.cash,
                        unrealized_pnl=unrealized,
                    )
                    self._equity_repo.create(point)

                    # Commit all changes before sleeping
                    self._conn.commit()

                    prev_bar_date = bar_date

                except Exception as e:
                    logger.error("Error in paper trading loop: %s", e)

                # Advance to next tick
                clock.advance()

            logger.info("Paper trading loop stopped cleanly")
            self._conn.commit()

        finally:
            # Restore signal handlers
            signal.signal(signal.SIGINT, old_sigint)
            signal.signal(signal.SIGTERM, old_sigterm)
