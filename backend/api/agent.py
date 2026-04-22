import json
from pydantic import BaseModel
from backend.db.database import getDb
from backend.db.models import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from backend.services.agent_manager import agent_manager
from fastapi import APIRouter, Depends, HTTPException, Request


router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class TaskRequest(BaseModel):
    """Request body for submitting a task to the agent."""

    message: str


@router.post("/{session_id}/task")
async def submitTask(
    session_id: str,
    body: TaskRequest,
    db: AsyncSession = Depends(getDb),
):
    """Start an agent task for the given session."""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await agent_manager.submitTask(session_id, body.message)

    await db.refresh(session)
    return {
        "status": "started",
        "display_num": session.display_num,
        "vnc_port": session.vnc_port,
        "token": session_id,
    }


@router.get("/{session_id}/stream")
async def streamEvents(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(getDb),
):
    """SSE endpoint streaming agent events to the frontend."""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def generator():
        async for event in agent_manager.getEventStream(session_id):
            if await request.is_disconnected():
                break
            yield json.dumps(event)

    return EventSourceResponse(generator())


@router.post("/{session_id}/stop")
async def stopTask(
    session_id: str,
    db: AsyncSession = Depends(getDb),
):
    """Cancel the running agent task for a session."""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await agent_manager.stopTask(session_id)
    return {"status": "stopped"}


@router.get("/{session_id}/vnc-info")
async def getVncInfo(
    session_id: str,
    db: AsyncSession = Depends(getDb),
):
    """Return VNC connection info for a session's container."""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    from backend.services.container_manager import container_manager

    info = container_manager.getContainerInfo(session_id)
    return {
        "display_num": 1,
        "vnc_port": info.vnc_port if info else session.vnc_port,
        "token": session_id,
    }
