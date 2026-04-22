import os
import asyncio
from typing import Any, Literal
from .base import BaseAnthropicTool, CLIResult, ToolError, ToolResult


class BashSession:
    """A persistent bash shell session."""

    command: str = "/bin/bash"

    def __init__(
        self,
        displayNum: int | None = None,
        username: str | None = None,
        homeDir: str | None = None,
    ):
        """Initialize session parameters without starting the shell."""
        self._started = False
        self._timedOut = False
        self._outputDelay: float = 0.2
        self._timeout: float = 120.0
        self._sentinel: str = "<<exit>>"
        self._displayNum = displayNum
        self._username = username
        self._homeDir = homeDir

    async def start(self):
        """Start the bash subprocess."""
        if self._started:
            return

        env = {**os.environ}
        if self._displayNum is not None:
            env["DISPLAY"] = f":{self._displayNum}"
        if self._homeDir:
            env["HOME"] = self._homeDir

        startDir = None
        if self._username:
            home = self._homeDir or "/home/" + self._username
            startDir = home
            cmd = (
                f"sudo -u {self._username} "
                f"env DISPLAY={env.get('DISPLAY', ':1')} "
                f"HOME={home} "
                f"/bin/bash"
            )
        else:
            cmd = self.command

        self._process = await asyncio.create_subprocess_shell(
            cmd,
            preexec_fn=os.setsid,
            shell=True,
            bufsize=0,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=startDir,
        )

        self._started = True

    def stop(self):
        """Terminate the bash shell."""
        if not self._started:
            raise ToolError("Session has not started.")
        if self._process.returncode is not None:
            return
        self._process.terminate()

    async def run(self, command: str):
        """Execute a command in the bash shell."""
        if not self._started:
            raise ToolError("Session has not started.")
        if self._process.returncode is not None:
            return ToolResult(
                system="tool must be restarted",
                error=f"bash has exited with returncode {self._process.returncode}",
            )
        if self._timedOut:
            raise ToolError(
                f"timed out: bash has not returned in {self._timeout} seconds and must be restarted",
            )

        assert self._process.stdin
        assert self._process.stdout
        assert self._process.stderr

        self._process.stdin.write(
            command.encode() + f"; echo '{self._sentinel}'\n".encode()
        )
        await self._process.stdin.drain()

        async def _read_until_sentinel():
            while True:
                await asyncio.sleep(self._outputDelay)
                buf = self._process.stdout._buffer.decode()
                if self._sentinel in buf:
                    return buf[: buf.index(self._sentinel)]

        try:
            output = await asyncio.wait_for(_read_until_sentinel(), timeout=self._timeout)
        except asyncio.TimeoutError:
            self._timedOut = True
            raise ToolError(
                f"timed out: bash has not returned in {self._timeout} seconds and must be restarted",
            ) from None

        if output.endswith("\n"):
            output = output[:-1]

        error = self._process.stderr._buffer.decode()
        if error.endswith("\n"):
            error = error[:-1]

        self._process.stdout._buffer.clear()
        self._process.stderr._buffer.clear()

        return CLIResult(output=output, error=error)


class BashTool20250124(BaseAnthropicTool):
    """A tool that allows the agent to run bash commands."""

    api_type: Literal["bash_20250124"] = "bash_20250124"
    name: Literal["bash"] = "bash"

    def __init__(
        self,
        display_num: int | None = None,
        username: str | None = None,
        home_dir: str | None = None,
        **kwargs,
    ):
        """Initialize with optional display, user, and home directory."""
        self._session = None
        self._displayNum = display_num
        self._username = username
        self._homeDir = home_dir
        super().__init__()

    def toParams(self) -> Any:
        """Return the API parameter representation."""
        return {
            "type": self.api_type,
            "name": self.name,
        }

    async def __call__(
        self,
        command: str | None = None,
        restart: bool = False,
        **kwargs,
    ):
        """Execute a bash command or restart the session."""
        if restart:
            if self._session:
                self._session.stop()
            self._session = BashSession(
                displayNum=self._displayNum,
                username=self._username,
                homeDir=self._homeDir,
            )
            await self._session.start()
            return ToolResult(system="tool has been restarted.")

        if self._session is None:
            self._session = BashSession(
                displayNum=self._displayNum,
                username=self._username,
                homeDir=self._homeDir,
            )
            await self._session.start()

        if command is not None:
            return await self._session.run(command)

        raise ToolError("no command provided.")


class BashTool20241022(BashTool20250124):
    """Backward-compatible alias for BashTool20250124."""

    api_type: Literal["bash_20250124"] = "bash_20250124"
