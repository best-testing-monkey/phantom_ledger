from datetime import datetime
from unittest.mock import patch

from phantom.engine.clock import LiveClock


class TestLiveClock:
    def test_now_returns_utc_datetime(self):
        """LiveClock.now() returns current UTC datetime."""
        clock = LiveClock(interval=1.0)
        now = clock.now()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None

    def test_is_done_always_false(self):
        """Paper trading never finishes; is_done() always returns False."""
        clock = LiveClock(interval=1.0)
        assert clock.is_done() is False

    def test_advance_computes_sleep_duration(self):
        """advance() computes correct sleep duration based on elapsed time."""
        with patch("phantom.engine.clock.time.monotonic") as mock_monotonic:
            with patch("phantom.engine.clock.time.sleep") as mock_sleep:
                # Init: monotonic() = 0.0
                # advance():
                #   elapsed = monotonic() - 0.0 = 0.2 - 0.0 = 0.2
                #   sleep_for = max(0, 1.0 - 0.2) = 0.8
                #   _last_tick = monotonic() = 0.2 (again in same call)
                # We need 2 calls: one for elapsed, one for _last_tick
                mock_monotonic.side_effect = [0.0, 0.2, 0.2]
                clock = LiveClock(interval=1.0)
                clock.advance()
                mock_sleep.assert_called_once()
                call_arg = mock_sleep.call_args[0][0]
                assert 0.75 < call_arg < 0.85  # Allow small floating point variance

    def test_advance_handles_elapsed_greater_than_interval(self):
        """advance() sleeps 0 if elapsed time exceeds interval."""
        with patch("phantom.engine.clock.time.monotonic") as mock_monotonic:
            with patch("phantom.engine.clock.time.sleep") as mock_sleep:
                # Init: monotonic() = 0.0
                # advance():
                #   elapsed = monotonic() - 0.0 = 1.5 - 0.0 = 1.5
                #   sleep_for = max(0, 1.0 - 1.5) = 0
                #   _last_tick = monotonic() = 1.5
                mock_monotonic.side_effect = [0.0, 1.5, 1.5]
                clock = LiveClock(interval=1.0)
                clock.advance()
                mock_sleep.assert_called_once_with(0.0)

    def test_advance_updates_last_tick(self):
        """advance() updates internal tick timer."""
        with patch("phantom.engine.clock.time.monotonic") as mock_monotonic:
            with patch("phantom.engine.clock.time.sleep") as mock_sleep:
                # Init: monotonic() = 0.0
                # First advance():
                #   elapsed = 0.3 - 0.0 = 0.3
                #   sleep_for = max(0, 1.0 - 0.3) = 0.7
                #   _last_tick = 0.3
                # Second advance():
                #   elapsed = 1.0 - 0.3 = 0.7
                #   sleep_for = max(0, 1.0 - 0.7) = 0.3
                #   _last_tick = 1.0
                mock_monotonic.side_effect = [0.0, 0.3, 0.3, 1.0, 1.0]
                clock = LiveClock(interval=1.0)
                clock.advance()

                mock_sleep.reset_mock()
                clock.advance()

                # Second advance should sleep ~0.3
                mock_sleep.assert_called_once()
                call_arg = mock_sleep.call_args[0][0]
                assert 0.25 < call_arg < 0.35
