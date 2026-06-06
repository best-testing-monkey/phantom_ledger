from __future__ import annotations

from phantom.costs.engine import CostEngine
from phantom.reports.metrics import CostSummary


def compare_broker_costs(
    positions: list, profile_names: list[str], profile_loader
) -> dict[str, CostSummary]:
    """Compare costs across multiple broker profiles for closed positions.

    Args:
        positions: All positions from the account
        profile_names: List of broker profile names to compare
        profile_loader: Callable that loads a profile by name (e.g., brokers_api.get)

    Returns:
        Dict mapping profile name to CostSummary
    """
    closed_positions = [
        p for p in positions if p.status == "closed" and p.exit_datetime is not None
    ]

    results = {}
    for profile_name in profile_names:
        profile = profile_loader(profile_name)
        engine = CostEngine(profile)

        commission = spread = slippage = overnight = fx = dividends = 0.0

        for pos in closed_positions:
            days_held = (pos.exit_datetime - pos.entry_datetime).days
            overnight_charge = days_held * profile.overnight.daily_rate if days_held > 0 else 0.0

            entry_cost = engine.entry_costs(
                price=pos.entry_price,
                quantity=pos.quantity,
                ticker=pos.ticker,
                instrument_type=pos.instrument_type,
            )
            exit_cost = engine.exit_costs(
                price=pos.exit_price or pos.entry_price,
                quantity=pos.quantity,
                ticker=pos.ticker,
                instrument_type=pos.instrument_type,
            )

            commission += entry_cost.commission + exit_cost.commission
            spread += entry_cost.spread + exit_cost.spread
            slippage += entry_cost.slippage + exit_cost.slippage
            fx += entry_cost.fx + exit_cost.fx
            overnight += overnight_charge
            dividends += pos.dividend_adjustments

        total_cost = commission + spread + slippage + overnight + fx + dividends

        results[profile_name] = CostSummary(
            total_commission=commission,
            total_spread=spread,
            total_slippage=slippage,
            total_overnight=overnight,
            total_fx=fx,
            total_dividends=dividends,
            total_cost=total_cost,
        )

    return results
