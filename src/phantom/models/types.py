from typing import Literal

AccountType = Literal["pattern", "manual", "algorithm", "aggregate"]
InstrumentType = Literal["stock", "cfd"]
Direction = Literal["long", "short"]
OrderType = Literal["market", "limit", "stop", "stop_limit", "trailing_stop", "oco"]
OrderStatus = Literal["pending", "triggered", "filled", "expired", "rejected", "cancelled"]
PositionStatus = Literal["open", "closed", "liquidated"]
CloseReason = Literal["tp", "sl", "trailing_stop", "max_time", "margin_call", "manual"]
