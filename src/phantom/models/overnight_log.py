from pydantic import BaseModel, Field

from phantom.utils.datetime import now_utc
from phantom.utils.ids import new_id


class OvernightLog(BaseModel):
    """Record of overnight financing charge applied to a position."""

    id: str = Field(default_factory=new_id)
    position_id: str
    account_id: str
    date: str  # ISO date "YYYY-MM-DD"
    rate: float
    charge_amount: float
    created_at: str = Field(default_factory=lambda: now_utc().isoformat())
