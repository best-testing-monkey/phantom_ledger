from dataclasses import dataclass, field

from phantom.models.account import Account
from phantom.models.equity_point import EquityPoint
from phantom.models.order import Order
from phantom.models.position import Position


@dataclass
class BacktestResult:
    account: Account
    equity_curve: list[EquityPoint] = field(default_factory=list)
    filled_orders: list[Order] = field(default_factory=list)
    closed_positions: list[Position] = field(default_factory=list)
