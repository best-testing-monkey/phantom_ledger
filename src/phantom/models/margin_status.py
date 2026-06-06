from typing import Literal

from pydantic import BaseModel


class MarginStatus(BaseModel, frozen=True):
    """Snapshot of account margin status."""

    level: float
    status: Literal["ok", "margin_call", "stop_out"]
    margin_call_level: float
    stop_out_level: float
