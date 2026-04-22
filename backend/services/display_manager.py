import os
import socket
import asyncio
import logging
import tempfile
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TOKEN_FILE = "/tmp/vnc_tokens.cfg"


@dataclass
class DisplayInfo:
    """Tracks a dynamically allocated display and its associated processes."""

    session_id: str
    display_num: int
    vnc_port: int
    xvfb_pid: int | None = None
    mutter_pid: int | None = None
    tint2_pid: int | None = None
    x11vnc_pid: int | None = None


class DisplayManager:
    """Manages dynamic X11 display allocation for concurrent agent sessions."""

    def __init__(self) -> None:
        """Initialize display tracking state and async lock."""
        self._displays: dict[str, DisplayInfo] = {}
        self._used_display_nums: set[int] = set()
        self._lock = asyncio.Lock()

    async def allocateDisplay(
        self,
        session_id: str,
        username: str | None = None,
        home_dir: str | None = None,
    ) -> DisplayInfo:
        """Allocate a fresh display for the given session, or return the existing one."""
        async with self._lock:
            if session_id in self._displays:
                return self._displays[session_id]

            display_num = self.nextAvailableDisplay()
            vnc_port = 5900 + display_num
            display_str = f":{display_num}"
            loop = asyncio.get_running_loop()

            w = os.environ.get("WIDTH", "1024")
            h = os.environ.get("HEIGHT", "768")
            xvfb = subprocess.Popen(
                [
                    "Xvfb",
                    display_str,
                    "-ac",
                    "-screen",
                    "0",
                    f"{w}x{h}x24",
                    "-retro",
                    "-dpi",
                    "96",
                    "-nolisten",
                    "tcp",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            for _ in range(30):
                ds = display_str
                r = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        ["xdpyinfo", "-display", ds],
                        capture_output=True,
                    ),
                )
                if r.returncode == 0:
                    break
                await asyncio.sleep(0.3)

            env = {**os.environ, "DISPLAY": display_str}

            if username and home_dir:
                mutter = subprocess.Popen(
                    [
                        "sudo",
                        "-u",
                        username,
                        "env",
                        f"DISPLAY={display_str}",
                        f"HOME={home_dir}",
                        "XDG_SESSION_TYPE=x11",
                        "mutter",
                        "--replace",
                        "--sm-disable",
                    ],
                    cwd=home_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                mutter = subprocess.Popen(
                    ["mutter", "--replace", "--sm-disable"],
                    env={**env, "XDG_SESSION_TYPE": "x11"},
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            if username and home_dir:
                tint2_rc = f"{home_dir}/.tint2/tint2rc"
                tint2 = subprocess.Popen(
                    [
                        "sudo",
                        "-u",
                        username,
                        "env",
                        f"DISPLAY={display_str}",
                        f"HOME={home_dir}",
                        "tint2",
                        "-c",
                        tint2_rc,
                    ],
                    cwd=home_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                tint2_rc = os.path.expanduser("~/.tint2/tint2rc")
                tint2 = subprocess.Popen(
                    ["tint2", "-c", tint2_rc],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            x11vnc = subprocess.Popen(
                [
                    "x11vnc",
                    "-display",
                    display_str,
                    "-forever",
                    "-shared",
                    "-wait",
                    "50",
                    "-rfbport",
                    str(vnc_port),
                    "-nopw",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            vp = vnc_port
            for _ in range(30):
                ready = await loop.run_in_executor(
                    None,
                    lambda: self.isPortOpen(vp),
                )
                if ready:
                    break
                await asyncio.sleep(0.3)

            info = DisplayInfo(
                session_id=session_id,
                display_num=display_num,
                vnc_port=vnc_port,
                xvfb_pid=xvfb.pid,
                mutter_pid=mutter.pid,
                tint2_pid=tint2.pid,
                x11vnc_pid=x11vnc.pid,
            )
            self._displays[session_id] = info
            self._used_display_nums.add(display_num)
            self.writeTokenFile()

            logger.info(
                "Display :%d allocated for session %s (VNC port %d)",
                display_num,
                session_id,
                vnc_port,
            )
            return info

    async def releaseDisplay(self, session_id: str) -> None:
        """Release the display previously allocated to the given session."""
        async with self._lock:
            info = self._displays.pop(session_id, None)
            if not info:
                return
            self.killDisplayProcesses(info)
            self._used_display_nums.discard(info.display_num)
            self.writeTokenFile()
            logger.info(
                "Display :%d released for session %s",
                info.display_num,
                session_id,
            )

    def getDisplayInfo(self, session_id: str) -> DisplayInfo | None:
        """Return display info for a session, or None if none is allocated."""
        return self._displays.get(session_id)

    async def cleanupAll(self) -> None:
        """Release every allocated display (used at shutdown)."""
        async with self._lock:
            for info in self._displays.values():
                self.killDisplayProcesses(info)
            self._displays.clear()
            self._used_display_nums.clear()
            self.writeTokenFile()
            logger.info("All displays cleaned up")

    def nextAvailableDisplay(self) -> int:
        """Return the lowest unused display number starting from 1."""
        num = 1
        while num in self._used_display_nums:
            num += 1
        return num

    @staticmethod
    def isPortOpen(port: int) -> bool:
        """Check whether a TCP port on localhost is accepting connections."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", port)) == 0

    @staticmethod
    def killDisplayProcesses(info: DisplayInfo) -> None:
        """Kill all processes associated with a display and clean lock files."""
        for pid in (info.x11vnc_pid, info.tint2_pid, info.mutter_pid, info.xvfb_pid):
            if pid:
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass
        for path in (
            f"/tmp/.X{info.display_num}-lock",
            f"/tmp/.X11-unix/X{info.display_num}",
        ):
            try:
                os.remove(path)
            except OSError:
                pass

    def writeTokenFile(self) -> None:
        """Atomically rewrite the websockify token file."""
        lines = [
            f"{sid}: localhost:{info.vnc_port}" for sid, info in self._displays.items()
        ]
        content = "\n".join(lines) + ("\n" if lines else "")
        fd, tmp = tempfile.mkstemp(dir="/tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.replace(tmp, TOKEN_FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


display_manager = DisplayManager()
