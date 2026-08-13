from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import statistics

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
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0


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


def _daily_returns(curve: list[EquityPoint]) -> list[float]:
    """Resample equity curve to daily (last equity per day) and compute returns."""
    if len(curve) < 2:
        return []

    daily_equity = {}
    for pt in curve:
        date_key = pt.timestamp.date()
        daily_equity[date_key] = pt.equity

    sorted_dates = sorted(daily_equity.keys())
    if len(sorted_dates) < 2:
        return []

    returns = []
    for i in range(1, len(sorted_dates)):
        prev_equity = daily_equity[sorted_dates[i - 1]]
        curr_equity = daily_equity[sorted_dates[i]]
        ret = (curr_equity / prev_equity) - 1
        returns.append(ret)

    return returns


def _sharpe(returns: list[float], rfr: float = 0.0) -> float:
    """Calculate annualized Sharpe ratio. Returns 0.0 if std==0 or < 2 returns."""
    if len(returns) < 2:
        return 0.0

    mean_ret = statistics.mean(returns)
    try:
        std_ret = statistics.stdev(returns)
    except statistics.StatisticsError:
        return 0.0

    if std_ret == 0:
        return 0.0

    excess_return = mean_ret - rfr / 252
    return excess_return / std_ret * (252**0.5)


def _sortino(returns: list[float], rfr: float = 0.0) -> float:
    """Calculate annualized Sortino ratio using downside deviation. Returns inf if no downside."""
    if len(returns) < 2:
        return 0.0

    mean_ret = statistics.mean(returns)
    threshold = rfr / 252
    downside_returns = [r for r in returns if r < threshold]

    if not downside_returns:
        return float("inf")

    downside_dev = (statistics.mean([r**2 for r in downside_returns])) ** 0.5
    if downside_dev == 0:
        return float("inf")

    excess_return = mean_ret - threshold
    return excess_return / downside_dev * (252**0.5)


def calculate_metrics(
    equity_curve: list[EquityPoint], risk_free_rate: float = 0.0
) -> EquityMetrics:
    if len(equity_curve) < 2:
        raise ValidationError("Equity curve too short to compute metrics")
    initial = equity_curve[0].equity
    final = equity_curve[-1].equity
    days = (equity_curve[-1].timestamp - equity_curve[0].timestamp).days
    years = days / 365.25
    total_return = (final / initial - 1) * 100
    # A leveraged/margin equity curve can go to or below zero (final <= 0),
    # not just toward it -- (final / initial) is then <= 0, and raising a
    # non-positive base to the non-integer exponent (1 / years) returns a
    # Python complex number, which later fails EquityMetrics' float
    # validation. Total wipeout (or worse) is -100% CAGR by convention;
    # only compute the real power when the base is actually positive.
    if final <= 0:
        cagr = -100.0
    else:
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

    returns = _daily_returns(equity_curve)
    sharpe = _sharpe(returns, risk_free_rate)
    sortino = _sortino(returns, risk_free_rate)

    return EquityMetrics(
        total_return_pct=total_return,
        cagr_pct=cagr,
        max_drawdown_pct=max_dd,
        max_drawdown_duration_days=max_dd_days,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
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


def build_aggregate_curve(child_accounts: list, all_positions: list[any]) -> list[EquityPoint]:
    """Build an aggregate equity curve from child accounts and their positions."""
    starting_equity = sum(acc.initial_capital for acc in child_accounts)

    closed_positions = [
        p for p in all_positions if p.status == "closed" and p.exit_datetime is not None
    ]
    closed_positions.sort(key=lambda p: p.exit_datetime)

    curve = []
    equity = starting_equity
    for pos in closed_positions:
        equity += pos.realized_pnl or 0.0
        curve.append(EquityPoint(timestamp=pos.exit_datetime, equity=equity))

    return curve


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
