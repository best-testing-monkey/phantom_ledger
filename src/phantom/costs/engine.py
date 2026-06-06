from dataclasses import dataclass

from phantom.models.broker import BrokerProfile


@dataclass(frozen=True)
class CostBreakdown:
    commission: float
    spread: float
    slippage: float
    fx: float
    total: float


class CostEngine:
    def __init__(self, profile: BrokerProfile):
        self._profile = profile

    def entry_costs(
        self,
        price: float,
        quantity: float,
        ticker: str,
        instrument_type: str,
        atr: float | None = None,
        hour_utc: int | None = None,
        fx_required: bool = False,
    ) -> CostBreakdown:
        return self._compute(price, quantity, atr, hour_utc, fx_required)

    def exit_costs(
        self,
        price: float,
        quantity: float,
        ticker: str,
        instrument_type: str,
        atr: float | None = None,
        hour_utc: int | None = None,
        fx_required: bool = False,
    ) -> CostBreakdown:
        return self._compute(price, quantity, atr, hour_utc, fx_required)

    def _compute(
        self,
        price: float,
        quantity: float,
        atr: float | None,
        hour_utc: int | None,
        fx_required: bool,
    ) -> CostBreakdown:
        commission = self._profile.commission.calculate(
            quantity=quantity, price=price, monthly_volume=0
        )
        spread = self._profile.spread.calculate(
            price=price, quantity=quantity, atr=atr, hour_utc=hour_utc
        )
        slippage = self._profile.slippage.calculate(price=price, quantity=quantity)
        fx = price * quantity * self._profile.fx_conversion_pct if fx_required else 0.0
        total = commission + spread + slippage + fx
        return CostBreakdown(
            commission=commission,
            spread=spread,
            slippage=slippage,
            fx=fx,
            total=total,
        )
