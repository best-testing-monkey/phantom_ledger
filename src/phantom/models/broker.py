from typing import Any

from pydantic import BaseModel


class CommissionModel(BaseModel):
    model_type: str
    fixed_fee: float | None = None
    per_share_fee: float | None = None
    tiers: list[dict[str, Any]] | None = None
    monthly_free_volume: float | None = None


class SpreadModel(BaseModel):
    model_type: str
    fixed_spread_pct: float | None = None


class SlippageModel(BaseModel):
    model_type: str
    fixed_pct: float | None = None
    volume_factor: float | None = None


class OvernightModel(BaseModel):
    long_markup_pct: float
    short_markup_pct: float
    day_divisor: int
    rate_source: str
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
    fx_conversion_pct: float
    fx_base_currency: str
    min_order_size: float
    max_leverage: float
    trading_hours: TradingHoursConfig
    supported_instruments: list[str]
