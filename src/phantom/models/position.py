from datetime import datetime

from pydantic import BaseModel, Field

from phantom.models.types import CloseReason, Direction, InstrumentType, PositionStatus
from phantom.utils.datetime import now_utc
from phantom.utils.ids import new_id


class Position(BaseModel):
    id: str = Field(default_factory=new_id)
    account_id: str
    ticker: str
    instrument_type: InstrumentType
    direction: Direction
    entry_order_id: str
    entry_price: float
    entry_datetime: datetime
    quantity: float
    notional: float

    take_profit: float | None = None
    stop_loss: float | None = None
    trailing_stop_amount: float | None = None
    trailing_stop_pct: float | None = None
    trailing_stop_peak: float | None = None
    max_close_datetime: datetime | None = None

    commission_entry: float = 0.0
    commission_exit: float = 0.0
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    overnight_costs: float = 0.0
    dividend_adjustments: float = 0.0
    fx_conversion_cost: float = 0.0

    margin_required: float = 0.0
    leverage: float = 1.0

    exit_price: float | None = None
    exit_datetime: datetime | None = None
    realized_pnl: float | None = None
    status: PositionStatus = "open"
    close_reason: CloseReason | None = None

    pattern_tag: str | None = None
    replay_completed_at: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
