from pydantic import BaseModel, Field

from phantom.utils.ids import new_id


class EquityPoint(BaseModel):
    id: str = Field(default_factory=new_id)
    account_id: str
    timestamp: str
    equity: float
    cash: float = 0.0
    unrealized_pnl: float = 0.0
    used_margin: float = 0.0
    drawdown_pct: float = 0.0
