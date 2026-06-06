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
            price=price, quantity=quantity, atr=atr, hour_utc=hour_utc, bid=None, ask=None
        )
        slippage = self._profile.slippage.calculate(price=price, quantity=quantity, adv=None)
        fx = price * quantity * self._profile.fx_conversion_pct if fx_required else 0.0
        total = commission + spread + slippage + fx
        return CostBreakdown(
            commission=commission,
            spread=spread,
            slippage=slippage,
            fx=fx,
            total=total,
        )

    def overnight_cost(
        self,
        notional: float,
        direction: str,
        reference_rate: float,
    ) -> float:
        """Calculate overnight financing charge for a CFD position.

        Args:
            notional: Position notional value (quantity * price)
            direction: "long" or "short"
            reference_rate: Current reference rate (SOFR, ESTR, etc.)

        Returns:
            Overnight charge amount
        """
        return self._profile.overnight.calculate(
            notional=notional,
            direction=direction,
            reference_rate=reference_rate,
        )

    def dividend_adjustment(
        self,
        gross: float,
        direction: str,
        instrument_type: str,
        country: str = "US",
    ) -> float:
        """Calculate dividend adjustment for a position.

        Args:
            gross: Gross dividend amount (dividend_per_share * quantity)
            direction: "long" or "short"
            instrument_type: "stock" or "cfd"
            country: Country code for withholding rate lookup

        Returns:
            Adjustment amount (may be positive or negative)
        """
        if instrument_type == "stock":
            withholding_rate = self._profile.dividend.withholding_rates.get(country, 0.15)
            return gross * (1 - withholding_rate)
        elif direction == "long":
            return gross * self._profile.dividend.cfd_dividend_adjustment
        else:  # short CFD
            return -(gross * self._profile.dividend.cfd_short_dividend_charge)
