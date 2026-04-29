from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import aiosqlite
from database import DB_PATH
from services.auth import decode_token
from services.terminal_bridge import run_terminal
import services.session_manager as sm
import services.docker_manager as dm

router = APIRouter(tags=["terminal"])


@router.websocket("/ws/{session_id}")
async def terminal_ws(websocket: WebSocket, session_id: str, token: str = Query(...)):
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = int(payload["sub"])

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, is_active FROM users WHERE id = ?", (user_id,)
        ) as cur:
            user = await cur.fetchone()

    if not user or not user["is_active"]:
        await websocket.close(code=4001, reason="User not found")
        return

    session = await sm.get_session(session_id)
    if not session or session["user_id"] != user_id:
        await websocket.close(code=4004, reason="Session not found")
        return

    if session["status"] == "terminated":
        await websocket.close(code=4004, reason="Session already terminated")
        return

    container_id = session.get("container_id")
    if not container_id or not await dm.is_container_running(container_id):
        await websocket.close(code=4002, reason="Container not running")
        return

    try:
        await run_terminal(websocket, session_id, container_id)
    except WebSocketDisconnect:
        pass
    finally:
        sm.active_connections.pop(session_id, None)
