from typing import Any, Literal

from pydantic import BaseModel


class CommissionModel(BaseModel):
    model_type: Literal["fixed", "per_share", "tiered", "zero"]
    fixed_fee: float | None = None
    per_share: float | None = None
    per_share_min: float | None = None
    per_share_max_pct: float | None = None
    tiers: list[dict[str, Any]] | None = None
    monthly_free_volume: float | None = None

    def calculate(self, quantity: float, price: float, monthly_volume: float) -> float:
        if self.model_type == "fixed":
            return self.fixed_fee or 0.0
        if self.model_type == "per_share":
            per_share_rate = self.per_share or 0.0
            commission = max(self.per_share_min or 0.0, quantity * per_share_rate)
            if self.per_share_max_pct is not None:
                max_commission = self.per_share_max_pct * price * quantity
                commission = min(commission, max_commission)
            return commission
        if self.model_type == "tiered":
            if not self.tiers:
                return 0.0
            tier_rate = 0.0
            for tier in self.tiers:
                if monthly_volume < tier.get("up_to", float("inf")):
                    tier_rate = tier.get("rate", 0.0)
                    break
            else:
                tier_rate = self.tiers[-1].get("rate", 0.0)
            return quantity * price * tier_rate
        if self.model_type == "zero":
            if self.monthly_free_volume is None:
                return 0.0
            if monthly_volume < self.monthly_free_volume:
                return 0.0
            if self.fixed_fee is not None:
                return self.fixed_fee
            per_share_rate = self.per_share or 0.0
            return quantity * per_share_rate
        raise NotImplementedError(f"Commission type {self.model_type!r} not implemented")


class SpreadModel(BaseModel):
    model_type: Literal["fixed", "dynamic", "market"]
    fixed_spread_pct: float | None = None
    base_spread_pct: float | None = None
    volatility_multiplier: float | None = None
    time_of_day_curve: dict[str, float] | None = None

    def calculate(
        self,
        price: float,
        quantity: float,
        atr: float | None = None,
        hour_utc: int | None = None,
        bid: float | None = None,
        ask: float | None = None,
    ) -> float:
        if self.model_type == "fixed":
            return (self.fixed_spread_pct or 0.0) * price * quantity
        if self.model_type == "dynamic":
            base = self.base_spread_pct or 0.0
            vol_factor = 0.0
            if atr is not None and price > 0:
                vol_factor = (self.volatility_multiplier or 0.0) * atr / price
            time_multiplier = 1.0
            if hour_utc is not None and self.time_of_day_curve:
                keys = sorted(int(k) for k in self.time_of_day_curve.keys())
                chosen = keys[0]
                for k in keys:
                    if k <= hour_utc:
                        chosen = k
                time_multiplier = self.time_of_day_curve[str(chosen)]
            return base * time_multiplier * (1 + vol_factor) * price * quantity
        if self.model_type == "market":
            if bid is not None and ask is not None:
                return (ask - bid) / 2 * quantity
            return (self.fixed_spread_pct or 0.0) * price * quantity
        raise NotImplementedError(f"Spread type {self.model_type!r} not implemented")


class SlippageModel(BaseModel):
    model_type: Literal["fixed_pct", "volume_based"]
    fixed_pct: float | None = None
    base_pct: float | None = None
    exponent: float | None = None

    def calculate(self, price: float, quantity: float, adv: float | None = None) -> float:
        if self.model_type == "fixed_pct":
            return (self.fixed_pct or 0.0) * price * quantity
        if self.model_type == "volume_based":
            if adv is None or adv == 0.0:
                return (self.fixed_pct or 0.0) * price * quantity
            base_pct = self.base_pct or 0.0
            exponent = self.exponent or 1.0
            slippage_pct = base_pct * ((quantity / adv) ** exponent)
            return slippage_pct * price * quantity
        raise NotImplementedError(f"Slippage type {self.model_type!r} not implemented")


class OvernightModel(BaseModel):
    long_markup_pct: float
    short_markup_pct: float
    day_divisor: int
    rate_source: Literal["sofr", "estr", "sonia", "manual"]
    manual_rate: float | None = None

    def calculate(
        self, notional: float, direction: str, reference_rate: float, day_of_week: int
    ) -> float:
        if direction == "long":
            markup = self.long_markup_pct
        else:
            markup = self.short_markup_pct
        daily_rate = (reference_rate + markup) / self.day_divisor
        charge = notional * daily_rate
        if day_of_week == 2:
            charge *= 3
        return charge


class MarginModel(BaseModel):
    default_margin_pct: float
    margin_call_level: float
    stop_out_level: float


class DividendModel(BaseModel):
    withholding_rates: dict[str, float]
    cfd_dividend_adjustment: float
    cfd_short_dividend_charge: float

    def calculate_stock_dividend(self, gross: float, country: str) -> tuple[float, float]:
        withholding_rate = self.withholding_rates.get(country, 0.0)
        withholding = gross * withholding_rate
        net_amount = gross - withholding
        return net_amount, withholding

    def calculate_cfd_adjustment(self, gross: float, direction: str) -> float:
        if direction == "long":
            return gross * self.cfd_dividend_adjustment
        else:
            return -(gross * self.cfd_short_dividend_charge)


class TradingHoursConfig(BaseModel):
    timezone: str
    open: str
    close: str
    pre_market: bool
    post_market: bool


class BrokerProfile(BaseModel):
    name: str
    commission: CommissionModel
    spread: SpreadModel
    slippage: SlippageModel
    overnight: OvernightModel
    margin: MarginModel
    dividend: DividendModel
    trading_hours: TradingHoursConfig
    fx_conversion_pct: float
    fx_base_currency: str
    min_order_size: float
    max_leverage: float
    supported_instruments: list[str]
