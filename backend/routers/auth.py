from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import aiosqlite
from database import get_db
from models.user import UserOut, TokenResponse
from services.auth import verify_password, create_access_token
from middleware.auth import get_current_user
from config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT id, username, hashed_password, is_active, is_admin FROM users WHERE username = ?",
        (form.username,),
    ) as cur:
        row = await cur.fetchone()

    if not row or not verify_password(form.password, row["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account deactivated")

    token = create_access_token(row["id"], bool(row["is_admin"]))
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_hours * 3600,
    )


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user), db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT id, username, email, is_active, is_admin, created_at, ssh_private_key FROM users WHERE id = ?",
        (user["id"],),
    ) as cur:
        row = await cur.fetchone()
    result = dict(row)
    result["has_ssh_key"] = bool(result.pop("ssh_private_key"))
    return result
