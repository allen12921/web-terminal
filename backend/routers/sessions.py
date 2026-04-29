from fastapi import APIRouter, Depends, HTTPException, status
from models.session import SessionOut
import services.session_manager as sm
from middleware.auth import get_current_user
from config import settings

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(user: dict = Depends(get_current_user)):
    session = await sm.create_session(user["id"])
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum {settings.max_sessions_per_user} sessions reached",
        )
    return session


@router.get("", response_model=list[SessionOut])
async def list_sessions(user: dict = Depends(get_current_user)):
    return await sm.list_user_sessions(user["id"])


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    session = await sm.get_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}", status_code=204)
async def terminate_session(session_id: str, user: dict = Depends(get_current_user)):
    session = await sm.get_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    await sm.terminate_session(session_id, "user_request")
