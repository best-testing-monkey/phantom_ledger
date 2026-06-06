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
        raise NotImplementedError(f"Spread type {self.model_type!r} not implemented")


class SlippageModel(BaseModel):
    model_type: Literal["fixed_pct", "volume_based"]
    fixed_pct: float | None = None
    volume_factor: float | None = None

    def calculate(self, price: float, quantity: float) -> float:
        if self.model_type == "fixed_pct":
            return (self.fixed_pct or 0.0) * price * quantity
        raise NotImplementedError(f"Slippage type {self.model_type!r} not implemented")


class OvernightModel(BaseModel):
    long_markup_pct: float
    short_markup_pct: float
    day_divisor: int
    rate_source: Literal["sofr", "estr", "sonia", "manual"]
    manual_rate: float | None = None


class MarginModel(BaseModel):
    default_margin_pct: float
    margin_call_level: float
    stop_out_level: float


class DividendModel(BaseModel):
    withholding_rates: dict[str, float]
    cfd_dividend_adjustment: float
    cfd_short_dividend_charge: float


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
