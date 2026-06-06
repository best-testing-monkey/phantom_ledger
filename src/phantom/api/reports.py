import sqlite3

from phantom.db.repositories.account_repo import AccountRepo
from phantom.db.repositories.position_repo import PositionRepo
from phantom.reports.metrics import (
    CostSummary,
    EquityPoint,
    aggregate_costs,
    calculate_metrics,
    calculate_trade_metrics,
)


class ReportAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._account_repo = AccountRepo(conn)
        self._position_repo = PositionRepo(conn)

    def account_metrics(self, account_name: str) -> dict:
        account = self._account_repo.get_by_name(account_name)
        positions = self._position_repo.list_by_account(account.id)
        closed = sorted(
            [p for p in positions if p.status == "closed" and p.exit_datetime],
            key=lambda p: p.exit_datetime,
        )
        equity = account.initial_capital
        curve = []
        for pos in closed:
            equity += pos.realized_pnl or 0.0
            curve.append(EquityPoint(timestamp=pos.exit_datetime, equity=equity))
        result = {}
        if len(curve) >= 2:
            result["equity"] = calculate_metrics(curve)
        if closed:
            result["trades"] = calculate_trade_metrics(positions)
        result["costs"] = aggregate_costs(positions)
        return result

    def cost_breakdown(self, account_name: str) -> CostSummary:
        account = self._account_repo.get_by_name(account_name)
        positions = self._position_repo.list_by_account(account.id)
        return aggregate_costs(positions)
