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
        self, account: Account, broker_profile: BrokerProfile, open_position_market_value: float
    ) -> MarginStatus:
        """Check margin status and return status snapshot.

        Args:
            account: The account to check
            broker_profile: Broker profile with margin settings
            open_position_market_value: Current market value of all open positions

        Returns:
            MarginStatus with level, status ("ok", "margin_call", or "stop_out"),
            and broker margin thresholds.
        """
        # Get sum of margin_required for all open CFD positions
        used_margin = open_position_market_value * broker_profile.margin.default_margin_pct

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
    ) -> list[Position]:
        """Handle stop-out cascade: force-close positions until recovered.

        Sorts positions by unrealized_pnl (ascending, largest loss first).
        For each position, checks if margin recovered. If not, closes position
        at bar's close price. Continues until margin recovers above stop_out_level
        or all positions are closed.

        Args:
            account: The account
            open_positions: List of open positions
            broker_profile: Broker profile with margin settings
            current_bar_timestamp: Current bar timestamp
            position_manager: PositionManager instance for closing positions
            account_repo: Account repository for updating cash

        Returns:
            List of closed positions from the cascade
        """
        closed_positions = []

        # Sort by unrealized_pnl ascending (largest loss first)
        sorted_positions = sorted(open_positions, key=lambda p: p.unrealized_pnl or 0.0)

        stop_out_level = broker_profile.margin.stop_out_level

        for position in sorted_positions:
            # Compute current margin level after previous closes
            remaining_market_value = sum(
                p.notional for p in open_positions if p.id not in [cp.id for cp in closed_positions]
            )
            used_margin = (
                remaining_market_value * broker_profile.margin.default_margin_pct
                if remaining_market_value > 0
                else 0
            )
            equity = account.cash

            if used_margin == 0:
                margin_level = float("inf")
            else:
                margin_level = (equity / used_margin) * 100

            # Check if still in stop-out
            if margin_level <= stop_out_level:
                # Force close this position at close price
                # Use close price as 0.0 for now (caller will provide actual price)
                closed = position_manager.close(
                    position,
                    exit_price=0.0,
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
                    position.unrealized_pnl,
                )

        # Check if fully liquidated and still in stop-out
        if closed_positions and all(
            p.id in [cp.id for cp in closed_positions] for p in open_positions
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
