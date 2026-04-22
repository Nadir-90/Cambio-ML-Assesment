import asyncio
import logging
from sqlalchemy import update
from backend.db.models import Session
from datetime import datetime, timezone
from collections.abc import AsyncGenerator
from backend.db.database import AsyncSessionLocal
from backend.services.agent_worker import AgentWorker
from backend.services.container_manager import container_manager


logger = logging.getLogger(__name__)


class AgentManager:
    """Singleton managing agent tasks, event queues, and SSE streams for all sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    async def persistMessages(
        self,
        session_id: str,
        messages: list,
        status: str,
    ) -> None:
        """Save the full message list and final status to the database."""
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Session)
                .where(Session.id == session_id)
                .values(
                    messages=messages,
                    status=status,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    async def submitTask(
        self,
        session_id: str,
        user_message: str,
    ) -> None:
        """Spawn a session container (if needed) and start an asyncio worker task."""
        async with AsyncSessionLocal() as db:
            session = await db.get(Session, session_id)
            username = (session.username if session else None) or (
                "agent_" + session_id.replace("-", "")[:8]
            )
            home_dir = (session.home_dir if session else None) or f"/home/{username}"

        container_info = container_manager.getContainerInfo(session_id)
        if not container_info:
            container_info = await container_manager.createSession(
                session_id,
                username=username,
                home_dir=home_dir,
            )

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Session)
                .where(Session.id == session_id)
                .values(
                    container_id=container_info.container_id,
                    display_num=1,
                    vnc_port=container_info.vnc_port,
                    username=username,
                    home_dir=home_dir,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        if session_id not in self._sessions:
            queue: asyncio.Queue = asyncio.Queue()
            worker = AgentWorker(
                session_id,
                queue,
                tool_server_url=container_info.tool_server_url,
                display_num=1,
                home_dir=home_dir,
            )
            self._sessions[session_id] = {
                "queue": queue,
                "worker": worker,
                "task": None,
            }
        else:
            entry = self._sessions[session_id]
            if entry["worker"]:
                entry["worker"].tool_server_url = container_info.tool_server_url
                entry["worker"].home_dir = home_dir

        entry = self._sessions[session_id]
        existing = entry.get("task")

        if existing and not existing.done():
            existing.cancel()
            try:
                await existing
            except (asyncio.CancelledError, Exception):
                pass

        task = asyncio.create_task(
            entry["worker"].run(user_message, self.persistMessages)
        )
        entry["task"] = task

    async def getEventStream(self, session_id: str) -> AsyncGenerator[dict, None]:
        """Yield events from the session queue, with heartbeats on timeout."""
        if session_id not in self._sessions:
            queue: asyncio.Queue = asyncio.Queue()
            self._sessions[session_id] = {"queue": queue, "worker": None, "task": None}

        queue = self._sessions[session_id]["queue"]

        yield {"type": "connected", "session_id": session_id}
        await asyncio.sleep(0)

        TERMINAL = {"completed", "error", "cancelled"}

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield event
                await asyncio.sleep(0)
                if event.get("type") in TERMINAL:
                    break
            except asyncio.TimeoutError:
                yield {"type": "heartbeat"}
                await asyncio.sleep(0)

    async def stopTask(self, session_id: str) -> None:
        """Cancel the running agent task and wait for it to finish."""
        entry = self._sessions.get(session_id)
        if not entry:
            return
        task = entry.get("task")
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def releaseSessionContainer(self, session_id: str) -> None:
        """Stop and remove the session container."""
        await container_manager.releaseSession(session_id)

    async def cleanupAll(self) -> None:
        """Stop all tasks and release all session containers."""
        for session_id, entry in list(self._sessions.items()):
            task = entry.get("task")
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        await container_manager.cleanupAll()


agent_manager = AgentManager()
