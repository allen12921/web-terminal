import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional
import aiosqlite
from fastapi import WebSocket
from config import settings
from database import DB_PATH
import services.docker_manager as dm


# session_id -> WebSocket (connected terminals)
active_connections: dict[str, WebSocket] = {}


def new_session_id() -> str:
    return str(uuid.uuid4())


async def create_session(user_id: int) -> dict:
    session_id = new_session_id()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE user_id = ? AND status IN ('pending','active','idle')",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if row["cnt"] >= settings.max_sessions_per_user:
                return None

        container_id = await dm.create_container(session_id)
        await db.execute(
            "INSERT INTO sessions (id, user_id, container_id, status) VALUES (?, ?, ?, 'active')",
            (session_id, user_id, container_id),
        )
        await db.commit()

        async with db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ) as cur:
            return dict(await cur.fetchone())


async def get_session(session_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_user_sessions(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions WHERE user_id = ? AND status IN ('pending','active','idle') ORDER BY created_at DESC",
            (user_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def list_all_sessions() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.*, u.username FROM sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.status IN ('pending','active','idle')
               ORDER BY s.created_at DESC""",
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def touch_session(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET last_activity = datetime('now'), status = 'active' WHERE id = ?",
            (session_id,),
        )
        await db.commit()


async def terminate_session(session_id: str, reason: str = "user_request"):
    ws = active_connections.pop(session_id, None)
    if ws:
        try:
            await ws.send_json({"type": "terminated", "reason": reason})
            await ws.close()
        except Exception:
            pass

    session = await get_session(session_id)
    if session and session.get("container_id"):
        await dm.destroy_container(session["container_id"])

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET status='terminated', terminated_at=datetime('now'), termination_reason=? WHERE id=?",
            (reason, session_id),
        )
        await db.commit()


async def cleanup_loop():
    while True:
        await asyncio.sleep(settings.cleanup_interval)
        try:
            await _run_cleanup()
        except Exception:
            pass


async def _run_cleanup():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Idle timeout
        async with db.execute(
            """SELECT id FROM sessions
               WHERE status IN ('active','idle','pending')
               AND (julianday('now') - julianday(last_activity)) * 86400 > ?""",
            (settings.idle_timeout,),
        ) as cur:
            idle = [r["id"] for r in await cur.fetchall()]

        for sid in idle:
            await terminate_session(sid, "idle_timeout")

        # Max session time
        async with db.execute(
            """SELECT id FROM sessions
               WHERE status IN ('active','idle','pending')
               AND (julianday('now') - julianday(created_at)) * 86400 > ?""",
            (settings.max_session_time,),
        ) as cur:
            expired = [r["id"] for r in await cur.fetchall()]

        for sid in expired:
            await terminate_session(sid, "max_session_time")

        # Orphan container recovery
        async with db.execute(
            "SELECT container_id FROM sessions WHERE status IN ('active','idle','pending')"
        ) as cur:
            known = {r["container_id"] for r in await cur.fetchall() if r["container_id"]}

    running = set(await dm.list_sandbox_containers())
    for cid in running - known:
        await dm.destroy_container(cid)


async def terminate_all_sessions():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM sessions WHERE status IN ('active','idle','pending')"
        ) as cur:
            sessions = [r["id"] for r in await cur.fetchall()]
    for sid in sessions:
        await terminate_session(sid, "server_shutdown")
