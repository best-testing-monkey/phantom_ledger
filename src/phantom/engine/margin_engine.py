from datetime import datetime
import logging

from phantom.db.repositories.account_repo import AccountRepo
from phantom.models.account import Account
from phantom.models.broker import BrokerProfile
from phantom.models.margin_status import MarginStatus
from phantom.models.position import Position
from phantom.utils.datetime import now_utc

logger = logging.getLogger(__name__)


class MarginEngine:
    """Margin level tracking and enforcement for CFD accounts."""

    def check(
        self, account: Account, broker_profile: BrokerProfile, open_positions: list[Position]
    ) -> MarginStatus:
        """Check margin status and return status snapshot.

        Args:
            account: The account to check
            broker_profile: Broker profile with margin settings
            open_positions: List of all open positions (any instrument_type).
                Only CFD positions contribute to used_margin; each position's
                own stored margin_required is used rather than recomputing a
                rate-based estimate.

        Returns:
            MarginStatus with level, status ("ok", "margin_call", or "stop_out"),
            and broker margin thresholds.
        """
        # Sum of margin_required for all open CFD positions
        used_margin = sum(p.margin_required for p in open_positions if p.instrument_type == "cfd")

        # Equity is current cash
        equity = account.cash

        # Margin level as percentage: equity / used_margin * 100
        if used_margin == 0:
            level = float("inf")
        else:
            level = (equity / used_margin) * 100

        # Determine status based on margin thresholds
        margin_call_level = broker_profile.margin.margin_call_level
        stop_out_level = broker_profile.margin.stop_out_level

        if level <= stop_out_level:
            status = "stop_out"
        elif level <= margin_call_level:
            status = "margin_call"
        else:
            status = "ok"

        return MarginStatus(
            level=level,
            status=status,
            margin_call_level=margin_call_level,
            stop_out_level=stop_out_level,
        )

    def handle_margin_call(
        self,
        account: Account,
        margin_status: MarginStatus,
        account_repo: AccountRepo,
        dispatcher=None,
    ) -> None:
        """Handle margin call warning: log, flag account, emit event.

        Sets account.margin_call_at only if not already set (idempotent).
        Does NOT close any positions.

        Args:
            account: The account
            margin_status: Current margin status
            account_repo: Account repository for persistence
            dispatcher: Optional event dispatcher for notifications
        """
        # Only set margin_call_at if not already set
        if account.margin_call_at is None:
            account.margin_call_at = now_utc()
            account_repo.update(account)

        # Log warning with %s formatting
        logger.warning(
            "Margin call warning for account %s: margin level %s%%, margin call level %s%%",
            account.id,
            margin_status.level,
            margin_status.margin_call_level,
        )

        # Emit event if dispatcher available
        if dispatcher is not None:
            dispatcher.emit(
                "margin_warning",
                {
                    "account_id": account.id,
                    "margin_level": margin_status.level,
                    "margin_call_level": margin_status.margin_call_level,
                    "timestamp": account.margin_call_at.isoformat(),
                },
            )

    def handle_stop_out(
        self,
        account: Account,
        open_positions: list[Position],
        broker_profile: BrokerProfile,
        current_bar_timestamp: datetime,
        position_manager,
        account_repo: AccountRepo,
        last_close: dict[str, float],
    ) -> list[Position]:
        """Handle stop-out cascade: force-close positions until recovered.

        Only CFD positions are candidates for forced closure (stock positions
        carry no real margin exposure and are never liquidated by this path).
        Sorts candidate positions by a real unrealized P&L (ascending, largest
        loss first) computed from last_close/entry_price/quantity/direction —
        Position.unrealized_pnl is a permanent 0.0 stub and is not used here.
        For each position, checks if margin recovered. If not, closes position
        at its ticker's last known close price. Continues until margin recovers
        above stop_out_level or all candidates are closed.

        Args:
            account: The account
            open_positions: List of open positions
            broker_profile: Broker profile with margin settings
            current_bar_timestamp: Current bar timestamp
            position_manager: PositionManager instance for closing positions
            account_repo: Account repository for updating cash
            last_close: Per-ticker last known Close price, used both to
                compute each candidate's real unrealized P&L for sort order
                and as the forced-close exit price (falls back to
                position.entry_price if a ticker was never observed).

        Returns:
            List of closed positions from the cascade
        """
        closed_positions = []

        def _unrealized_pnl(p: Position) -> float:
            current_price = last_close.get(p.ticker, p.entry_price)
            if p.direction == "long":
                return (current_price - p.entry_price) * p.quantity
            return (p.entry_price - current_price) * p.quantity

        # Only CFD positions carry real margin exposure and are eligible for
        # forced closure; stock positions must never be liquidated here.
        cfd_positions = [p for p in open_positions if p.instrument_type == "cfd"]

        # Sort by real unrealized P&L ascending (largest loss first)
        sorted_positions = sorted(cfd_positions, key=_unrealized_pnl)

        stop_out_level = broker_profile.margin.stop_out_level

        for position in sorted_positions:
            # Compute current margin level after previous closes, using each
            # remaining CFD position's own stored margin_required.
            used_margin = sum(
                p.margin_required
                for p in cfd_positions
                if p.id not in [cp.id for cp in closed_positions]
            )
            equity = account.cash

            if used_margin == 0:
                margin_level = float("inf")
            else:
                margin_level = (equity / used_margin) * 100

            # Check if still in stop-out
            if margin_level <= stop_out_level:
                # Force close this position at its ticker's last known close
                # price (falls back to entry price, never a fake zero).
                closed = position_manager.close(
                    position,
                    exit_price=last_close.get(position.ticker, position.entry_price),
                    close_reason="margin_call",
                    bar_timestamp=current_bar_timestamp,
                )
                closed_positions.append(closed)

                # Update account cash (deduct exit costs)
                # Note: position_manager.close() doesn't update account; caller must handle
                logger.info(
                    "Force-closed position %s for account %s due to stop-out: unrealized P&L %s",
                    position.id,
                    account.id,
                    _unrealized_pnl(position),
                )

        # Check if fully liquidated (all CFD candidates closed) and still in stop-out
        if closed_positions and all(
            p.id in [cp.id for cp in closed_positions] for p in cfd_positions
        ):
            used_margin = 0
            equity = account.cash
            if used_margin == 0:
                margin_level = float("inf")
            else:
                margin_level = (equity / used_margin) * 100

            if margin_level <= stop_out_level:
                logger.warning(
                    "Account %s fully liquidated but still below stop-out level: margin level %s%%",
                    account.id,
                    margin_level,
                )

        return closed_positions
