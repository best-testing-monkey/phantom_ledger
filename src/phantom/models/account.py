from datetime import datetime

from pydantic import BaseModel, Field

from phantom.models.types import AccountType
from phantom.utils.datetime import now_utc
from phantom.utils.ids import new_id


class Account(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    account_type: AccountType
    broker_profile_id: str
    base_currency: str = "EUR"
    initial_capital: float
    cash: float
    created_at: datetime = Field(default_factory=now_utc)
    pattern_tag: str | None = None
    algorithm_id: str | None = None
    algorithm_version: str | None = None
    algorithm_params: dict | None = None
    child_account_ids: list[str] | None = None
