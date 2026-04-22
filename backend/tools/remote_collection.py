import httpx
import logging
from typing import Any
from .base import ToolResult, ToolFailure
from .schemas import TOOL_SCHEMAS, ToolVersion

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 180.0


class RemoteToolCollection:
    """Executes tools via HTTP calls to the session container's tool server.

    Tool schemas (toParams) come from hardcoded Anthropic API specs in schemas.py.
    Actual execution is delegated to the session container — no tool code runs here.
    """

    def __init__(self, tool_server_url: str, tool_version: ToolVersion) -> None:
        self.tool_server_url = tool_server_url
        self._schemas = TOOL_SCHEMAS.get(tool_version, [])

    def toParams(self) -> list[dict]:
        """Return Anthropic API parameter schemas for all tools."""
        return self._schemas

    async def run(self, *, name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Execute a tool by posting to the session container's tool server."""
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{self.tool_server_url}/tools/{name}",
                    json=tool_input,
                )
                response.raise_for_status()
                data = response.json()
                return ToolResult(
                    output=data.get("output"),
                    error=data.get("error"),
                    base64_image=data.get("base64_image"),
                    system=data.get("system"),
                )
        except httpx.HTTPStatusError as e:
            logger.error("Tool server HTTP error for %s: %s", name, e)
            return ToolFailure(error=f"Tool server returned {e.response.status_code}")
        except Exception as e:
            logger.error("Remote tool call failed for %s: %s", name, e)
            return ToolFailure(error=f"Remote tool call failed: {e}")
