#!/usr/bin/env python3
"""Tool server running inside a session container.

Exposes the Computer, Bash, and Edit tools over HTTP so the main app
can execute them remotely without needing X11 or a desktop environment.
"""

import os
import sys

sys.path.insert(0, "/opt/cua-session")

import uvicorn
from fastapi import FastAPI
from typing import Any, cast
from tools.bash import BashTool20250124
from tools.edit import EditTool20250728
from tools.base import ToolResult, ToolError
from tools.computer import ComputerTool20250124

app = FastAPI()

DISPLAY_NUM = 1
SESSION_USERNAME = os.environ.get("SESSION_USERNAME", "computeruse")
SESSION_HOME = os.environ.get("SESSION_HOME", f"/home/{SESSION_USERNAME}")

_tool_instances = [
    ComputerTool20250124(display_num=DISPLAY_NUM, username=SESSION_USERNAME, home_dir=SESSION_HOME),
    BashTool20250124(display_num=DISPLAY_NUM, username=SESSION_USERNAME, home_dir=SESSION_HOME),
    EditTool20250728(display_num=DISPLAY_NUM, username=SESSION_USERNAME, home_dir=SESSION_HOME),
]

TOOLS: dict[str, Any] = {
    cast(dict[str, Any], t.toParams())["name"]: t
    for t in _tool_instances
}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tools/{tool_name}")
async def run_tool(tool_name: str, body: dict[str, Any]):
    tool = TOOLS.get(tool_name)
    if not tool:
        return {
            "output": None,
            "error": f"Unknown tool: {tool_name}",
            "base64_image": None,
            "system": None,
        }
    try:
        result: ToolResult = await tool(**body)
        return {
            "output": result.output,
            "error": result.error,
            "base64_image": result.base64_image,
            "system": result.system,
        }
    except ToolError as e:
        return {
            "output": None,
            "error": e.message,
            "base64_image": None,
            "system": None,
        }
    except Exception as e:
        return {
            "output": None,
            "error": str(e),
            "base64_image": None,
            "system": None,
        }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
