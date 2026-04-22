import httpx
import asyncio
from backend.config import settings
from backend.tools import ToolResult
from collections.abc import Callable
from datetime import datetime, timezone
from sqlalchemy import update as sa_update
from backend.db.models import Message, Session
from backend.db.database import AsyncSessionLocal
from anthropic.types.beta import BetaContentBlockParam
from backend.services.sampling_loop import APIProvider, samplingLoop


class AgentWorker:
    """Executes a single agent task within a session, streaming events via a queue."""

    def __init__(
        self,
        session_id: str,
        queue: asyncio.Queue,
        tool_server_url: str = "",
        display_num: int | None = None,
        home_dir: str | None = None,
    ) -> None:
        """Initialize with session ID, event queue, and session container info."""
        self.session_id = session_id
        self.queue = queue
        self.messages: list = []
        self.tool_server_url = tool_server_url
        self.display_num = display_num
        self.home_dir = home_dir

    def persistMessage(
        self,
        role: str,
        content: dict,
        message_type: str,
    ) -> None:
        """Fire-and-forget database write for a single message."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.writeMessage(role, content, message_type))
        except RuntimeError:
            pass

    async def writeMessage(
        self,
        role: str,
        content: dict,
        message_type: str,
    ) -> None:
        """Insert a message row into the database."""
        async with AsyncSessionLocal() as db:
            msg = Message(
                session_id=self.session_id,
                role=role,
                content=content,
                message_type=message_type,
            )
            db.add(msg)
            await db.commit()

    def sanitizeMessages(self) -> None:
        """Insert synthetic tool_results for unmatched tool_use blocks after cancellation."""
        if not self.messages:
            return

        patched: list = []
        for i, msg in enumerate(self.messages):
            patched.append(msg)

            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue

            tool_use_ids = [
                block["id"]
                for block in content
                if isinstance(block, dict) and block.get("type") == "tool_use"
            ]
            if not tool_use_ids:
                continue

            next_msg = self.messages[i + 1] if i + 1 < len(self.messages) else None
            answered_ids: set[str] = set()
            if next_msg and next_msg.get("role") == "user":
                next_content = next_msg.get("content", [])
                if isinstance(next_content, list):
                    answered_ids = {
                        block["tool_use_id"]
                        for block in next_content
                        if isinstance(block, dict)
                        and block.get("type") == "tool_result"
                        and "tool_use_id" in block
                    }

            missing_ids = [tid for tid in tool_use_ids if tid not in answered_ids]
            if not missing_ids:
                continue

            synthetic = [
                {
                    "type": "tool_result",
                    "tool_use_id": tid,
                    "content": "Tool execution was interrupted because the task was cancelled.",
                    "is_error": True,
                }
                for tid in missing_ids
            ]

            if next_msg is None or next_msg.get("role") != "user":
                patched.append({"role": "user", "content": synthetic})
            else:
                next_content = next_msg.get("content", [])
                if isinstance(next_content, list):
                    for item in reversed(synthetic):
                        next_content.insert(0, item)

        self.messages = patched

    def textChunkCallback(self, chunk: str) -> None:
        """Stream a text chunk to the frontend via the event queue."""
        self.queue.put_nowait({"type": "text_chunk", "text": chunk})

    def outputCallback(self, content_block: BetaContentBlockParam) -> None:
        """Handle a complete content block from the model response."""
        if isinstance(content_block, dict):
            block_type = content_block.get("type")
            if block_type == "text":
                text = content_block.get("text", "")
                if text:
                    self.persistMessage("assistant", {"text": text}, "text")
            elif block_type == "tool_use":
                self.queue.put_nowait(
                    {
                        "type": "tool_use",
                        "name": content_block.get("name"),
                        "id": content_block.get("id"),
                        "input": content_block.get("input"),
                    }
                )
                self.persistMessage(
                    "assistant",
                    {
                        "name": content_block.get("name"),
                        "id": content_block.get("id"),
                        "input": content_block.get("input"),
                    },
                    "tool_use",
                )

    def toolOutputCallback(self, result: ToolResult, tool_use_id: str) -> None:
        """Handle a tool execution result, sending it to the queue and database."""
        event: dict = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "output": result.output,
            "error": result.error,
        }
        if result.base64_image:
            event["screenshot"] = result.base64_image
        self.queue.put_nowait(event)
        content: dict = {
            "tool_use_id": tool_use_id,
            "output": result.output,
            "error": result.error,
        }
        if result.base64_image:
            content["screenshot"] = result.base64_image
        self.persistMessage("tool", content, "tool_result")

    def apiResponseCallback(
        self,
        request: httpx.Request,
        response: httpx.Response | object | None,
        error: Exception | None,
    ) -> None:
        """Forward API response status or errors to the event queue."""
        if error:
            self.queue.put_nowait({"type": "api_response", "error": str(error)})
        else:
            status = getattr(response, "status_code", None)
            self.queue.put_nowait({"type": "api_response", "status_code": status})

    async def run(self, user_message: str, db_callback: Callable) -> None:
        """Execute the agent sampling loop for a user message."""
        async with AsyncSessionLocal() as db:
            await db.execute(
                sa_update(Session)
                .where(Session.id == self.session_id)
                .values(status="running", updated_at=datetime.now(timezone.utc))
            )
            await db.commit()

        if not self.messages:
            async with AsyncSessionLocal() as db:
                session = await db.get(Session, self.session_id)
                if session and session.messages:
                    self.messages = list(session.messages)
                if session and not session.title:
                    title = user_message[:60].strip()
                    if len(user_message) > 60:
                        title += "..."
                    await db.execute(
                        sa_update(Session)
                        .where(Session.id == self.session_id)
                        .values(title=title, updated_at=datetime.now(timezone.utc))
                    )
                    await db.commit()

        self.sanitizeMessages()

        self.messages.append({"role": "user", "content": user_message})
        self.queue.put_nowait({"type": "user_message", "text": user_message})

        async with AsyncSessionLocal() as db:
            db.add(
                Message(
                    session_id=self.session_id,
                    role="user",
                    content={"text": user_message},
                    message_type="text",
                )
            )
            await db.commit()

        final_status = "active"
        try:
            self.messages = await samplingLoop(
                model="claude-sonnet-4-5-20250929",
                provider=APIProvider.ANTHROPIC,
                system_prompt_suffix="",
                messages=self.messages,
                output_callback=self.outputCallback,
                tool_output_callback=self.toolOutputCallback,
                api_response_callback=self.apiResponseCallback,
                api_key=settings.ANTHROPIC_API_KEY,
                max_tokens=16384,
                tool_version="computer_use_20250124",
                text_chunk_callback=self.textChunkCallback,
                display_num=self.display_num,
                home_dir=self.home_dir,
                tool_server_url=self.tool_server_url,
            )
            self.queue.put_nowait({"type": "completed"})
        except asyncio.CancelledError:
            self.queue.put_nowait({"type": "cancelled"})
            raise
        except Exception as exc:
            self.queue.put_nowait({"type": "error", "message": str(exc)})
        finally:
            await db_callback(self.session_id, self.messages, final_status)
