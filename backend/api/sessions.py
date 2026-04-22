import uuid
import logging
from backend.db.database import getDb
from datetime import datetime, timezone
from backend.db.models import Message, Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update
from backend.services.agent_manager import agent_manager
from backend.services.container_manager import container_manager
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.db.schemas import (
    ActivateRequest,
    MessageOut,
    SessionCreate,
    SessionDetail,
    SessionSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionDetail, status_code=201)
async def createSession(
    body: SessionCreate = SessionCreate(),
    db: AsyncSession = Depends(getDb),
):
    """Create a new session record. The session container is started on first task submission."""
    session = Session(
        id=str(uuid.uuid4()),
        title=body.title,
        status="new",
        messages=[],
        username=body.username or None,
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=list[SessionSummary])
async def listSessions(
    db: AsyncSession = Depends(getDb),
):
    """Return all sessions ordered by most recently updated."""
    result = await db.execute(select(Session).order_by(Session.updated_at.desc()))
    return result.scalars().all()


@router.get("/{session_id}", response_model=SessionDetail)
async def getSession(
    session_id: str,
    db: AsyncSession = Depends(getDb),
):
    """Return full details for a single session."""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def getSessionMessages(
    session_id: str,
    db: AsyncSession = Depends(getDb),
):
    """Return all persisted messages for a session in order."""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.id)
    )
    return result.scalars().all()


@router.delete("/{session_id}", status_code=204)
async def deleteSession(
    session_id: str,
    db: AsyncSession = Depends(getDb),
):
    """Delete a session, its messages, and its session container."""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        await agent_manager.stopTask(session_id)
        await agent_manager.releaseSessionContainer(session_id)
    except Exception:
        logger.exception("Error releasing session container for %s", session_id)

    msgs = await db.execute(select(Message).where(Message.session_id == session_id))
    for msg in msgs.scalars().all():
        await db.delete(msg)
    await db.delete(session)
    await db.commit()


@router.post("/{session_id}/activate", response_model=SessionDetail)
async def activateSession(
    session_id: str,
    body: ActivateRequest = ActivateRequest(),
    db: AsyncSession = Depends(getDb),
):
    """Activate a session by starting its session container."""
    target = await db.get(Session, session_id)
    if not target:
        raise HTTPException(status_code=404, detail="Session not found")

    if body.reset_display:
        try:
            await container_manager.releaseSession(session_id)
        except Exception:
            logger.exception("Failed to release container for session %s", session_id)

    username = target.username or ("agent_" + session_id.replace("-", "")[:8])
    home_dir = target.home_dir or f"/home/{username}"

    try:
        container_info = container_manager.getContainerInfo(session_id)
        if not container_info:
            container_info = await container_manager.createSession(
                session_id,
                username=username,
                home_dir=home_dir,
            )
        update_values: dict = {
            "updated_at": datetime.now(timezone.utc),
            "display_num": 1,
            "vnc_port": container_info.vnc_port,
            "container_id": container_info.container_id,
            "username": username,
            "home_dir": home_dir,
        }
    except Exception:
        logger.exception("Failed to start session container for %s", session_id)
        update_values = {"updated_at": datetime.now(timezone.utc)}

    if target.status in ("new", "switched"):
        update_values["status"] = "active"

    await db.execute(
        sa_update(Session).where(Session.id == session_id).values(**update_values)
    )
    await db.commit()
    await db.refresh(target)
    return target
