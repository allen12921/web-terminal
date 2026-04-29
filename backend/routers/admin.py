from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from database import get_db
from models.user import UserCreate, UserUpdate, UserOut
from models.session import AdminSessionOut
from services.auth import hash_password
import services.session_manager as sm
from middleware.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT id, username, email, is_active, is_admin, created_at FROM users ORDER BY created_at DESC"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    _: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        await db.execute(
            "INSERT INTO users (username, email, hashed_password, is_admin) VALUES (?, ?, ?, ?)",
            (body.username, body.email, hash_password(body.password), int(body.is_admin)),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    async with db.execute(
        "SELECT id, username, email, is_active, is_admin, created_at FROM users WHERE username = ?",
        (body.username,),
    ) as cur:
        return dict(await cur.fetchone())


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    fields, values = [], []
    if body.is_active is not None:
        fields.append("is_active = ?")
        values.append(int(body.is_active))
    if body.is_admin is not None:
        fields.append("is_admin = ?")
        values.append(int(body.is_admin))
    if body.email is not None:
        fields.append("email = ?")
        values.append(body.email)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.append(user_id)
    await db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
    await db.commit()

    async with db.execute(
        "SELECT id, username, email, is_active, is_admin, created_at FROM users WHERE id = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@router.get("/sessions", response_model=list[AdminSessionOut])
async def list_all_sessions(_: dict = Depends(require_admin)):
    return await sm.list_all_sessions()


@router.delete("/sessions/{session_id}", status_code=204)
async def force_terminate(session_id: str, _: dict = Depends(require_admin)):
    session = await sm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await sm.terminate_session(session_id, "admin_terminated")
