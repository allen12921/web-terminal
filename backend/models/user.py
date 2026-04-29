from pydantic import BaseModel
from typing import Optional


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    is_admin: bool = False


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    email: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: str
    has_ssh_key: bool = False


class SSHKeyUpdate(BaseModel):
    ssh_private_key: Optional[str] = None


class SSHKeyStatus(BaseModel):
    has_private_key: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
