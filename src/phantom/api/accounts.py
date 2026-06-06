from __future__ import annotations

import sqlite3
import threading

try:
    import pandas as pd
except ImportError:
    pd = None

from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.db.repositories.equity_repo import EquityRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.errors import NotFoundError, ValidationError
from phantom.models.account import Account, MarginSummary
from phantom.models.types import AccountType
from phantom.reports.equity_curve import combine_equity_curves


class AccountAPI:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock | None = None):
        self._conn = conn
        self._repo = AccountRepo(conn)
        self._broker_repo = BrokerRepo(conn)
        self._lock = lock or threading.RLock()

    def create(
        self,
        name: str,
        account_type: AccountType,
        broker: str,
        capital: float,
        currency: str = "EUR",
        pattern_tag: str | None = None,
        algorithm_id: str | None = None,
        algorithm_version: str | None = None,
        algorithm_params: dict | None = None,
        child_account_ids: list[str] | None = None,
    ) -> Account:
        with self._lock:
            self._broker_repo.get_by_name(broker)
            broker_id = self._broker_repo.get_id_by_name(broker)
            if account_type == "pattern" and not pattern_tag:
                raise ValidationError("pattern_tag is required for pattern accounts")
            if account_type == "algorithm" and not algorithm_id:
                raise ValidationError("algorithm_id is required for algorithm accounts")
            account = Account(
                name=name,
                account_type=account_type,
                broker_profile_id=broker_id,
                base_currency=currency,
                initial_capital=capital,
                cash=capital,
                pattern_tag=pattern_tag,
                algorithm_id=algorithm_id,
                algorithm_version=algorithm_version,
                algorithm_params=algorithm_params,
                child_account_ids=child_account_ids,
            )
            return self._repo.create(account)

    def list(self, account_type: str | None = None) -> list[Account]:
        return self._repo.list(account_type=account_type)

    def get(self, id_or_name: str) -> Account:
        try:
            return self._repo.get(id_or_name)
        except NotFoundError:
            return self._repo.get_by_name(id_or_name)

    def delete(self, account_id: str) -> None:
        with self._lock:
            self._repo.delete(account_id)

    def get_margin_summary(self, account_name: str) -> MarginSummary:
        """
        Get margin tracking summary for an account.

        Computes used_margin as the sum of margin_required for all open CFD positions,
        equity as account.cash, and derived metrics free_margin and margin_level.

        For accounts with no open CFD positions, returns zeros.

        Args:
            account_name: Account name

        Returns:
            MarginSummary with margin metrics

        Raises:
            NotFoundError: If account not found
        """
        account = self.get(account_name)
        position_repo = PositionRepo(self._conn)

        # Get all open positions for this account
        open_positions = position_repo.list_by_account(account.id, status="open")

        # Sum margin_required for all open positions (CFD positions have margin_required > 0)
        used_margin = sum(p.margin_required for p in open_positions)

        # Equity is the current cash balance
        equity = account.cash

        # Free margin is equity minus used margin
        free_margin = equity - used_margin

        # Margin level = equity / used_margin, or inf if no margin used
        if used_margin == 0:
            margin_level = float("inf")
        else:
            margin_level = equity / used_margin

        return MarginSummary(
            used_margin=used_margin,
            free_margin=free_margin,
            equity=equity,
            margin_level=margin_level,
        )

    def get_aggregate_equity(self, account_name: str):
        """
        Get aggregated equity curve for an account and its children.

        For non-aggregate accounts, returns the account's own equity curve.
        For aggregate accounts, combines child account equity curves using
        outer join with forward-fill.

        Args:
            account_name: Account name

        Returns:
            pandas Series with combined equity values indexed by timestamp

        Raises:
            ValidationError: If called on an aggregate account with no children
            ImportError: If pandas is not installed
        """
        if pd is None:
            raise ImportError("pandas is required for equity curve operations")

        account = self.get(account_name)
        equity_repo = EquityRepo(self._conn)

        if account.account_type == "aggregate":
            if not account.child_account_ids or len(account.child_account_ids) == 0:
                raise ValidationError(f"Aggregate account '{account_name}' has no child accounts")

            child_curves = []
            for child_id in account.child_account_ids:
                try:
                    child_account = self._repo.get(child_id)
                    points = equity_repo.list(child_account.id)
                    if points:
                        series = pd.Series(
                            [p.equity for p in points],
                            index=pd.DatetimeIndex([p.timestamp for p in points]),
                        )
                        child_curves.append(series)
                except NotFoundError:
                    continue

            if not child_curves:
                raise ValidationError(
                    f"Aggregate account '{account_name}' has no child accounts with equity data"
                )

            return combine_equity_curves(child_curves)
        else:
            # Non-aggregate account: return its own equity curve
            points = equity_repo.list(account.id)
            if not points:
                return pd.Series(dtype=float)
            return pd.Series(
                [p.equity for p in points],
                index=pd.DatetimeIndex([p.timestamp for p in points]),
            )
