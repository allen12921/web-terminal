from pydantic import BaseModel
from typing import Optional


class SessionCreate(BaseModel):
    pass


class SessionOut(BaseModel):
    id: str
    user_id: int
    container_id: Optional[str]
    status: str
    created_at: str
    last_activity: str
    terminated_at: Optional[str] = None
    termination_reason: Optional[str] = None


class AdminSessionOut(SessionOut):
    username: str
