from datetime import datetime

from pydantic import BaseModel, Field

from phantom.models.types import Direction, InstrumentType, OrderStatus, OrderType
from phantom.utils.datetime import now_utc
from phantom.utils.ids import new_id


class Order(BaseModel):
    id: str = Field(default_factory=new_id)
    account_id: str
    ticker: str
    instrument_type: InstrumentType
    direction: Direction
    order_type: OrderType
    quantity: float
    status: OrderStatus = "pending"

    limit_price: float | None = None
    stop_price: float | None = None
    trailing_amount: float | None = None
    trailing_pct: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None

    created_at: datetime = Field(default_factory=now_utc)
    triggered_at: datetime | None = None
    filled_at: datetime | None = None
    fill_price: float | None = None
    good_til: datetime | None = None
    max_close_datetime: datetime | None = None
    rejection_reason: str | None = None

    position_id: str | None = None
