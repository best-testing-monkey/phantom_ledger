from pydantic import BaseModel, Field

from phantom.utils.datetime import now_utc
from phantom.utils.ids import new_id


class DividendLog(BaseModel):
    """Record of dividend adjustment applied to a position."""

    id: str = Field(default_factory=new_id)
    position_id: str
    account_id: str
    ex_date: str  # ISO date "YYYY-MM-DD"
    dividend_per_share: float
    adjustment_amount: float
    created_at: str = Field(default_factory=lambda: now_utc().isoformat())
