from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import aiosqlite
from database import get_db, DB_PATH
from services.auth import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: aiosqlite.Connection = Depends(get_db),
):
    def unauthorized(detail="Not authenticated"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    if not credentials:
        unauthorized()

    payload = decode_token(credentials.credentials)
    if not payload:
        unauthorized("Invalid or expired token")

    user_id = int(payload["sub"])
    async with db.execute(
        "SELECT id, username, email, is_active, is_admin FROM users WHERE id = ?", (user_id,)
    ) as cur:
        row = await cur.fetchone()

    if not row or not row["is_active"]:
        unauthorized("User not found or deactivated")

    return dict(row)


async def require_admin(user: dict = Depends(get_current_user)):
    if not user["is_admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user
