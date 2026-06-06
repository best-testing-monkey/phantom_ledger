from pydantic import BaseModel, Field

from phantom.utils.ids import new_id


class Note(BaseModel):
    id: str = Field(default_factory=new_id)
    position_id: str
    account_id: str | None = None
    title: str
    file_path: str
    content_size: int = 0
    created_at: str
    updated_at: str
