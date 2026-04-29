from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from database import get_db
from models.user import SSHKeyStatus, SSHKeyUpdate
from middleware.auth import get_current_user
from services.ssh_utils import validate_private_key

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/ssh-key", response_model=SSHKeyStatus)
async def get_ssh_key_status(
    user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT ssh_private_key FROM users WHERE id = ?",
        (user["id"],),
    ) as cur:
        row = await cur.fetchone()

    if not row:
        return SSHKeyStatus()

    return SSHKeyStatus(has_private_key=bool(row["ssh_private_key"]))


@router.put("/ssh-key", status_code=204)
async def save_ssh_key(
    body: SSHKeyUpdate,
    user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    fields_set = getattr(body, "model_fields_set", set())
    updates: dict[str, str | None] = {}

    if "ssh_private_key" in fields_set:
        priv = (body.ssh_private_key or "").strip()
        if priv and not validate_private_key(priv):
            raise HTTPException(status_code=422, detail="Invalid SSH private key format")
        updates["ssh_private_key"] = priv or None

    if not updates:
        return

    await db.execute(
        f"UPDATE users SET {', '.join(f'{field} = ?' for field in updates)} WHERE id = ?",
        (*updates.values(), user["id"]),
    )
    await db.commit()


@router.delete("/ssh-key", status_code=204)
async def delete_ssh_key(
    user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute(
        "UPDATE users SET ssh_private_key = NULL WHERE id = ?",
        (user["id"],),
    )
    await db.commit()
