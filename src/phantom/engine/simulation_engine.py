from datetime import datetime, timezone
import logging
import signal
import sqlite3
from threading import Event

import pandas as pd

from phantom.costs.engine import CostEngine
from phantom.data.provider import DataProvider
from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
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
        fine_data_provider=None,
    ):
        self._conn = conn
        self._data_provider = data_provider
        self._cost_engine = cost_engine
        self._fine_data_provider = fine_data_provider
        self._account_repo = AccountRepo(conn)
        self._order_repo = OrderRepo(conn)
        self._position_repo = PositionRepo(conn)
        self._equity_repo = EquityRepo(conn)
        self._overnight_log_repo = OvernightLogRepo(conn)
        self._dividend_log_repo = DividendLogRepo(conn)
        self._margin_engine = MarginEngine()
        self._broker_repo = BrokerRepo(conn)
        self._order_manager = OrderManager(
            order_repo=self._order_repo,
            account_repo=self._account_repo,
            cost_engine=cost_engine,
            broker_repo=self._broker_repo,
        )
        self._position_manager = PositionManager(
            position_repo=self._position_repo,
            account_repo=self._account_repo,
            cost_engine=cost_engine,
            overnight_log_repo=self._overnight_log_repo,
            dividend_log_repo=self._dividend_log_repo,
        )

    # ------------------------------------------------------------------
    # Shared multi-ticker helpers
    #
    # DataProvider.get_bars() is single-ticker only, so every one of
    # run_backtest / run_paper / run_paper_tick needs to fetch bars once per
    # ticker and then, at each timestep, evaluate orders/positions/equity
    # against EACH ticker's OWN bar rather than one shared bar borrowed from
    # tickers[0]. These helpers centralize that logic so the three methods
    # don't each duplicate (and each separately risk re-breaking) it.
    # ------------------------------------------------------------------

    def _fetch_all_ticker_bars(
        self, tickers: list[str], start: datetime, end: datetime
    ) -> dict[str, pd.DataFrame]:
        """Fetch bars for every ticker individually via DataProvider.get_bars().

        Returns a dict of {ticker: DataFrame} containing only tickers that
        actually returned non-empty data; empty results are logged and
        skipped rather than raising.
        """
        ticker_bars: dict[str, pd.DataFrame] = {}
        for ticker in tickers:
            df = self._data_provider.get_bars(ticker, start, end)
            if df is None or df.empty:
                logger.warning(
                    "No bars returned for ticker %s in range %s to %s; skipping",
                    ticker,
                    start,
                    end,
                )
                continue
            ticker_bars[ticker] = df
        return ticker_bars

    def _evaluate_pending_orders(
        self, active_orders: list, bars_today: dict[str, pd.Series]
    ) -> list:
        """Group pending orders by ticker and evaluate each group against its
        OWN ticker's bar (never against another ticker's bar).

        Orders whose ticker has no bar this step are simply left pending —
        they get re-evaluated on a later step once their ticker has data.
        """
        orders_by_ticker: dict[str, list] = {}
        for order in active_orders:
            orders_by_ticker.setdefault(order.ticker, []).append(order)

        new_fills: list = []
        for ticker, orders_for_ticker in orders_by_ticker.items():
            bar = bars_today.get(ticker)
            if bar is None:
                continue
            new_fills.extend(self._order_manager.evaluate(bar, orders_for_ticker))
        return new_fills

    @staticmethod
    def _mark_to_market(open_positions: list, last_close: dict[str, float]) -> tuple[float, float]:
        """Compute market_value/unrealized P&L using each position's OWN
        ticker's last known Close price (carry-forward), falling back to
        entry_price only if that ticker was somehow never observed.
        """
        market_value = sum(
            p.quantity * last_close.get(p.ticker, p.entry_price) for p in open_positions
        )
        unrealized = sum(
            (last_close.get(p.ticker, p.entry_price) - p.entry_price) * p.quantity
            if p.direction == "long"
            else (p.entry_price - last_close.get(p.ticker, p.entry_price)) * p.quantity
            for p in open_positions
        )
        return market_value, unrealized

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

        ticker_bars = self._fetch_all_ticker_bars(tickers, start, end)
        if not ticker_bars:
            account = self._account_repo.get(account_id)
            return BacktestResult(account=account)

        # Master trading-day index: union of every ticker's own index, so a
        # day only one ticker trades (e.g. crypto on a weekend) still gets a
        # clock step, without forcing every OTHER ticker to have a bar too.
        master_index = pd.DatetimeIndex(
            sorted(set().union(*(df.index for df in ticker_bars.values())))
        )
        clock = BacktestClock(master_index)
        filled_orders: list = []
        rejected_orders: list = []
        closed_positions: list = []
        last_close: dict[str, float] = {}

        while not clock.is_done():
            current_time = clock.now()
            # Use the raw index value (not the UTC-parsed current_time) for
            # per-ticker lookups, since a ticker's own DataFrame index may not
            # round-trip identically through parse_datetime(); this mirrors
            # how the original single-ticker code indexed via
            # `price_data.index[clock._pos]` rather than `current_time`.
            raw_ts = master_index[clock._pos]

            bars_today: dict[str, pd.Series] = {}
            for ticker, df in ticker_bars.items():
                if raw_ts in df.index:
                    bar_for_ticker = df.loc[raw_ts]
                    bars_today[ticker] = bar_for_ticker
                    last_close[ticker] = float(bar_for_ticker["Close"])

            pending = self._order_repo.list_by_account(account_id, status="pending")
            active, expired = self._order_manager.expire_orders(pending, current_time)

            for exp_order in expired:
                self._order_repo.update_status(exp_order.id, "expired")

            new_fills = self._evaluate_pending_orders(active, bars_today)
            for filled_order in new_fills:
                filled_order_obj, position = self._order_manager.handle_fill_or_reject(
                    filled_order, self._position_repo
                )
                if position is None:
                    logger.info(
                        "Order %s rejected at fill time: %s",
                        filled_order_obj.id,
                        filled_order_obj.rejection_reason,
                    )
                    rejected_orders.append(filled_order_obj)
                    continue
                filled_orders.append(filled_order_obj)
                logger.info(
                    "Order %s filled at %.2f", filled_order_obj.id, filled_order_obj.fill_price
                )

            open_positions = self._position_repo.list_by_account(account_id, status="open")
            for position in open_positions:
                bar_for_position = bars_today.get(position.ticker)
                if bar_for_position is None:
                    # No bar for this position's ticker today - defer to the
                    # next step where its ticker has data.
                    continue
                result = self._position_manager.determine_close(
                    position, bar_for_position, fine_data_provider=self._fine_data_provider
                )
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
                    cash_return = self._position_manager.close_cash_return(
                        position, closed, exit_costs
                    )
                    acct = acct.model_copy(update={"cash": acct.cash + cash_return})
                    self._account_repo.update(acct)
                    closed_positions.append(self._position_repo.get(position.id))

            open_positions = self._position_repo.list_by_account(account_id, status="open")
            account = self._account_repo.get(account_id)
            market_value, unrealized = self._mark_to_market(open_positions, last_close)
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
            rejected_orders=rejected_orders,
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

        Note: this operates on position.notional and a reference rate, never
        on any bar's price, so it is not affected by the multi-ticker bar bug
        (there is no "wrong ticker's price" it could pick up).
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

        Note: this already calls self._data_provider.get_dividends() per
        position.ticker (not a shared bar), so it was already correct with
        respect to the multi-ticker bug and needed no changes here.
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
        current_time: datetime,
        last_close: dict[str, float] | None = None,
    ) -> list:
        """Check margin status and handle margin calls / stop-outs.

        Args:
            account: Account to check
            open_positions: List of open positions
            broker_profile: BrokerProfile with margin settings
            current_time: Timestamp to use for any forced-close records
                (previously derived from a single shared bar's .name; now
                passed explicitly since there is no longer one shared bar).
            last_close: Per-ticker last known Close price. Used so that, if a
                stop-out cascade forces a position closed, its exit costs are
                computed against ITS OWN ticker's price rather than a
                borrowed price from a different ticker's bar. Defaults to an
                empty dict (falls back to 0.0 per position, matching the
                previous behavior's `current_bar.get("Close", 0.0)` default).

        Returns:
            Updated list of open positions (after any forced closes)
        """
        if last_close is None:
            last_close = {}

        if not open_positions:
            return open_positions

        # Only check if account has CFD positions
        has_cfd = any(p.instrument_type == "cfd" for p in open_positions)
        if not has_cfd:
            return open_positions

        margin_status = self._margin_engine.check(account, broker_profile, open_positions)

        if margin_status.status == "stop_out":
            closed = self._margin_engine.handle_stop_out(
                account=account,
                open_positions=open_positions,
                broker_profile=broker_profile,
                current_bar_timestamp=current_time,
                position_manager=self._position_manager,
                account_repo=self._account_repo,
                last_close=last_close,
            )

            # Credit back cash and update account, using each closed
            # position's OWN ticker's last known Close price.
            for closed_pos in closed:
                close_price = last_close.get(closed_pos.ticker, 0.0)
                exit_costs = self._cost_engine.exit_costs(
                    price=close_price,
                    quantity=closed_pos.quantity,
                    ticker=closed_pos.ticker,
                    instrument_type=closed_pos.instrument_type,
                )
                account.cash += self._position_manager.close_cash_return(
                    closed_pos, closed_pos, exit_costs
                )
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
        last_close: dict[str, float] = {}

        try:
            while not stop_event.is_set():
                current_time = clock.now()
                current_time_str = to_iso(current_time)
                bar_date = current_time_str.split("T")[0]

                if not tickers:
                    logger.warning("No tickers specified for paper trading")
                    break

                try:
                    # Fetch current bar for every ticker
                    bar_day = parse_datetime(bar_date)
                    ticker_bars = self._fetch_all_ticker_bars(tickers, bar_day, bar_day)

                    if not ticker_bars:
                        logger.debug("No bars available for %s on %s", tickers, bar_date)
                        clock.advance()
                        continue

                    bars_today: dict[str, pd.Series] = {}
                    for ticker, df in ticker_bars.items():
                        bar_for_ticker = df.iloc[-1]
                        bars_today[ticker] = bar_for_ticker
                        last_close[ticker] = float(bar_for_ticker["Close"])

                    # Evaluate pending orders
                    pending = self._order_repo.list_by_account(account_id, status="pending")
                    active, expired = self._order_manager.expire_orders(pending, current_time)

                    for exp_order in expired:
                        self._order_repo.update_status(exp_order.id, "expired")
                        logger.info("Order %s expired", exp_order.id)

                    new_fills = self._evaluate_pending_orders(active, bars_today)
                    for filled_order in new_fills:
                        filled_order_obj, position = self._order_manager.handle_fill_or_reject(
                            filled_order, self._position_repo
                        )
                        if position is None:
                            logger.info(
                                "Order %s rejected at fill time: %s",
                                filled_order_obj.id,
                                filled_order_obj.rejection_reason,
                            )
                            continue
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
                        bar_for_position = bars_today.get(position.ticker)
                        if bar_for_position is None:
                            continue
                        result = self._position_manager.determine_close(position, bar_for_position)
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
                            cash_return = self._position_manager.close_cash_return(
                                position, closed, exit_costs
                            )
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
                        account, open_positions, broker_profile, current_time, last_close
                    )

                    # Record equity point
                    account = self._account_repo.get(account_id)
                    open_positions = self._position_repo.list_by_account(account_id, status="open")
                    market_value, unrealized = self._mark_to_market(open_positions, last_close)
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

    def run_paper_tick(
        self,
        account_id: str,
        tickers: list[str],
    ) -> None:
        """Execute a single paper trading tick (used by scheduler).

        Fetches live bars, evaluates orders, updates positions, applies
        overnight costs, dividends, and margin checks. Does not commit
        (caller is responsible for transaction management).

        Args:
            account_id: Account ID to trade
            tickers: List of tickers to fetch bars for
        """
        from phantom.models.broker import BrokerProfile

        account = self._account_repo.get(account_id)
        profile_row = self._account_repo._conn.execute(
            "SELECT config_json FROM broker_profiles WHERE id = ?",
            (account.broker_profile_id,),
        ).fetchone()

        if profile_row is None:
            raise ValueError(f"Broker profile not found: {account.broker_profile_id}")

        broker_profile = BrokerProfile.model_validate_json(profile_row[0])

        current_time = datetime.now(timezone.utc)
        current_time_str = to_iso(current_time)
        bar_date = current_time_str.split("T")[0]

        if not tickers:
            logger.warning("No tickers specified for paper trading")
            return

        try:
            # Fetch current bar for every ticker
            bar_day = parse_datetime(bar_date)
            ticker_bars = self._fetch_all_ticker_bars(tickers, bar_day, bar_day)

            if not ticker_bars:
                logger.debug("No bars available for %s on %s", tickers, bar_date)
                return

            bars_today: dict[str, pd.Series] = {}
            last_close: dict[str, float] = {}
            for ticker, df in ticker_bars.items():
                bar_for_ticker = df.iloc[-1]
                bars_today[ticker] = bar_for_ticker
                last_close[ticker] = float(bar_for_ticker["Close"])

            # Evaluate pending orders
            pending = self._order_repo.list_by_account(account_id, status="pending")
            active, expired = self._order_manager.expire_orders(pending, current_time)

            for exp_order in expired:
                self._order_repo.update_status(exp_order.id, "expired")
                logger.info("Order %s expired", exp_order.id)

            new_fills = self._evaluate_pending_orders(active, bars_today)
            for filled_order in new_fills:
                filled_order_obj, position = self._order_manager.handle_fill_or_reject(
                    filled_order, self._position_repo
                )
                if position is None:
                    logger.info(
                        "Order %s rejected at fill time: %s",
                        filled_order_obj.id,
                        filled_order_obj.rejection_reason,
                    )
                    continue
                logger.info(
                    "Order %s filled at %.2f",
                    filled_order_obj.id,
                    filled_order_obj.fill_price,
                )

            # Reload account and positions
            account = self._account_repo.get(account_id)
            open_positions = self._position_repo.list_by_account(account_id, status="open")

            # Get previous bar date from last equity point if available
            prev_equity_points = self._equity_repo.list(account_id)
            prev_bar_date = None
            if prev_equity_points:
                prev_timestamp_str = prev_equity_points[-1].timestamp
                prev_bar_date = prev_timestamp_str.split("T")[0]

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
                open_positions = self._position_repo.list_by_account(account_id, status="open")

            # Apply dividends
            self._apply_dividends(account, open_positions, bar_date, broker_profile)
            account = self._account_repo.get(account_id)
            open_positions = self._position_repo.list_by_account(account_id, status="open")

            # Update positions and check TP/SL
            for position in open_positions:
                bar_for_position = bars_today.get(position.ticker)
                if bar_for_position is None:
                    continue
                result = self._position_manager.determine_close(position, bar_for_position)
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
                    cash_return = self._position_manager.close_cash_return(
                        position, closed, exit_costs
                    )
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
                account, open_positions, broker_profile, current_time, last_close
            )

            # Record equity point
            account = self._account_repo.get(account_id)
            open_positions = self._position_repo.list_by_account(account_id, status="open")
            market_value, unrealized = self._mark_to_market(open_positions, last_close)
            equity = account.cash + market_value
            point = EquityPoint(
                account_id=account_id,
                timestamp=current_time_str,
                equity=equity,
                cash=account.cash,
                unrealized_pnl=unrealized,
            )
            self._equity_repo.create(point)

        except Exception as e:
            logger.error("Error in paper trading tick: %s", e, exc_info=True)
            raise
