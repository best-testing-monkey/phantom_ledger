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


class SpreadModel(BaseModel):
    model_type: Literal["fixed", "dynamic", "market"]
    fixed_spread_pct: float | None = None
    base_spread_pct: float | None = None
    volatility_multiplier: float | None = None
    time_of_day_curve: dict[str, float] | None = None


class SlippageModel(BaseModel):
    model_type: Literal["fixed_pct", "volume_based"]
    fixed_pct: float | None = None
    volume_factor: float | None = None


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
