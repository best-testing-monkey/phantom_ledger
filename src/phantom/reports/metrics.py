from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from phantom.errors import ValidationError


@dataclass
class EquityPoint:
    timestamp: datetime
    equity: float


class EquityMetrics(BaseModel, frozen=True):
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    max_drawdown_duration_days: int


class TradeMetrics(BaseModel, frozen=True):
    trade_count: int
    win_count: int
    loss_count: int
    win_rate_pct: float
    avg_win: float
    avg_loss: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    expectancy: float


class CostSummary(BaseModel, frozen=True):
    total_commission: float = 0.0
    total_spread: float = 0.0
    total_slippage: float = 0.0
    total_overnight: float = 0.0
    total_fx: float = 0.0
    total_dividends: float = 0.0
    total_cost: float = 0.0


def calculate_metrics(equity_curve: list[EquityPoint]) -> EquityMetrics:
    if len(equity_curve) < 2:
        raise ValidationError("Equity curve too short to compute metrics")
    initial = equity_curve[0].equity
    final = equity_curve[-1].equity
    days = (equity_curve[-1].timestamp - equity_curve[0].timestamp).days
    years = days / 365.25
    total_return = (final / initial - 1) * 100
    cagr = ((final / initial) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    peak = initial
    peak_ts = equity_curve[0].timestamp
    max_dd = 0.0
    max_dd_days = 0
    for pt in equity_curve:
        if pt.equity > peak:
            peak = pt.equity
            peak_ts = pt.timestamp
        dd = (peak - pt.equity) / peak * 100
        dd_days = (pt.timestamp - peak_ts).days
        max_dd = max(max_dd, dd)
        max_dd_days = max(max_dd_days, dd_days)
    return EquityMetrics(
        total_return_pct=total_return,
        cagr_pct=cagr,
        max_drawdown_pct=max_dd,
        max_drawdown_duration_days=max_dd_days,
    )


def calculate_trade_metrics(positions) -> TradeMetrics:
    closed = [p for p in positions if p.status == "closed" and p.realized_pnl is not None]
    if not closed:
        raise ValidationError("No closed positions to compute trade metrics")
    wins = [p.realized_pnl for p in closed if p.realized_pnl > 0]
    losses = [p.realized_pnl for p in closed if p.realized_pnl <= 0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    profit_factor = gross_profit / abs(gross_loss) if gross_loss != 0.0 else float("inf")
    n = len(closed)
    win_rate = len(wins) / n
    loss_rate = len(losses) / n
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = abs(gross_loss) / len(losses) if losses else 0.0
    expectancy = avg_win * win_rate - avg_loss * loss_rate
    return TradeMetrics(
        trade_count=n,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate_pct=win_rate * 100,
        avg_win=avg_win,
        avg_loss=avg_loss,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        expectancy=expectancy,
    )


def aggregate_costs(positions) -> CostSummary:
    commission = spread = slippage = overnight = fx = dividends = 0.0
    for pos in positions:
        commission += pos.commission_entry + pos.commission_exit
        spread += pos.spread_cost
        slippage += pos.slippage_cost
        overnight += pos.overnight_costs
        fx += pos.fx_conversion_cost
        dividends += pos.dividend_adjustments
    total = commission + spread + slippage + overnight + fx + dividends
    return CostSummary(
        total_commission=commission,
        total_spread=spread,
        total_slippage=slippage,
        total_overnight=overnight,
        total_fx=fx,
        total_dividends=dividends,
        total_cost=total,
    )
