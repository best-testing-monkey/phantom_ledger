import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from phantom.utils.datetime import now_utc

logger = logging.getLogger(__name__)


class PaperTradeScheduler:
    def __init__(self, engine, interval_seconds: int, conn=None, profile=None) -> None:
        """Initialize a paper trading scheduler.

        Args:
            engine: SimulationEngine instance with run_paper_tick() method
            interval_seconds: Interval between ticks in seconds
            conn: Database connection for state persistence
            profile: BrokerProfile for market hours awareness
        """
        self._engine = engine
        self._interval = interval_seconds
        self._conn = conn
        self._profile = profile
        self._scheduler = BlockingScheduler()

    def start(self) -> None:
        """Start the scheduler (blocks until stopped)."""
        self._scheduler.add_job(
            self._run_tick,
            trigger=IntervalTrigger(seconds=self._interval),
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self._scheduler.shutdown(wait=False)

    def _run_tick(self) -> None:
        """Run a single paper trading tick with market hours awareness and state persistence."""
        if not self._is_market_open():
            logger.debug("Market closed, skipping tick")
            return

        try:
            self._engine.run_paper_tick()
            if self._conn:
                self._conn.commit()
        except Exception as e:
            logger.error("Paper trade tick failed: %s", e, exc_info=True)
            if self._conn:
                self._conn.rollback()

    def _is_market_open(self) -> bool:
        """Check if the market is currently open based on broker profile.

        Returns:
            True if market is open or profile has no trading hours, False otherwise.
        """
        if self._profile is None or self._profile.trading_hours is None:
            return True

        trading_hours = self._profile.trading_hours

        try:
            # Get current UTC time
            now = now_utc()

            # Convert to broker's timezone
            tz = ZoneInfo(trading_hours.timezone)
            now_local = now.astimezone(tz)

            # Check weekday (0=Monday, 6=Sunday)
            weekday = now_local.weekday()

            # Parse open and close times (HH:MM format expected)
            open_parts = trading_hours.open.split(":")
            close_parts = trading_hours.close.split(":")
            open_time = (int(open_parts[0]), int(open_parts[1]))
            close_time = (int(close_parts[0]), int(close_parts[1]))

            current_time = (now_local.hour, now_local.minute)

            # Check if weekday is within trading (assuming weekday_mask is for NYSE: Mon-Fri)
            # For now, we assume standard Mon-Fri trading (0-4)
            # TODO: Parse weekday_mask from profile if it exists
            if weekday >= 5:  # Saturday or Sunday
                return False

            # Check if time is within trading hours
            if current_time < open_time or current_time >= close_time:
                return False

            return True

        except Exception as e:
            logger.warning("Failed to check market hours: %s", e)
            # If we can't determine market hours, assume open
            return True
