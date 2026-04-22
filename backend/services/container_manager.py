import os
import time
import socket
import asyncio
import logging
import docker
import docker.errors
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SESSION_IMAGE = os.environ.get("SESSION_IMAGE", "cua-session:latest")
SESSION_NETWORK = os.environ.get("SESSION_NETWORK", "cua-network")
VNC_TOKEN_FILE = "/tmp/vnc_tokens.cfg"


@dataclass
class ContainerInfo:
    """Tracks a running session container."""

    container_id: str
    container_name: str
    tool_server_url: str
    vnc_port: int = 5900


class ContainerManager:
    """Manages per-session Docker containers that host the desktop environment and tool server."""

    def __init__(self) -> None:
        self._client: docker.DockerClient | None = None
        self._containers: dict[str, ContainerInfo] = {}

    def _getClient(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _containerName(self, session_id: str) -> str:
        return f"cua-session-{session_id.replace('-', '')}"

    async def createSession(
        self,
        session_id: str,
        username: str,
        home_dir: str | None = None,
    ) -> ContainerInfo:
        """Spawn a session container and return its connection info."""
        existing = self._containers.get(session_id)
        if existing:
            return existing

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None, self._startContainer, session_id, username, home_dir
        )
        self._containers[session_id] = info
        self._writeTokenFile()
        return info

    def _startContainer(
        self, session_id: str, username: str, home_dir: str | None
    ) -> ContainerInfo:
        client = self._getClient()
        resolved_home = home_dir or f"/home/{username}"
        name = self._containerName(session_id)

        # Remove any leftover container with the same name
        try:
            old = client.containers.get(name)
            old.remove(force=True)
        except docker.errors.NotFound:
            pass

        container = client.containers.run(
            SESSION_IMAGE,
            detach=True,
            name=name,
            environment={
                "SESSION_USERNAME": username,
                "SESSION_HOME": resolved_home,
                "DISPLAY": ":1",
                "DISPLAY_NUM": "1",
                "WIDTH": os.environ.get("WIDTH", "1024"),
                "HEIGHT": os.environ.get("HEIGHT", "768"),
            },
            network=SESSION_NETWORK,
        )

        logger.info("Started session container %s (id=%s)", name, container.short_id)
        self._waitForVnc(name)

        return ContainerInfo(
            container_id=container.id,
            container_name=name,
            tool_server_url=f"http://{name}:8001",
            vnc_port=5900,
        )

    def _waitForVnc(self, container_name: str, timeout: int = 60) -> None:
        """Block until port 5900 accepts connections or timeout expires."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                s = socket.create_connection((container_name, 5900), timeout=2)
                s.close()
                logger.info("VNC ready on %s:5900", container_name)
                return
            except (socket.error, OSError):
                time.sleep(1)
        logger.warning("VNC did not become ready on %s within %ds", container_name, timeout)

    def _writeTokenFile(self) -> None:
        """Rewrite the websockify token file with all active sessions."""
        lines = [
            f"{sid}: {info.container_name}:5900"
            for sid, info in self._containers.items()
        ]
        try:
            with open(VNC_TOKEN_FILE, "w") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
        except OSError as e:
            logger.warning("Could not write VNC token file: %s", e)

    async def releaseSession(self, session_id: str) -> None:
        """Stop and remove the session container."""
        info = self._containers.pop(session_id, None)
        if not info:
            return
        self._writeTokenFile()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._stopContainer, info)

    def _stopContainer(self, info: ContainerInfo) -> None:
        try:
            container = self._getClient().containers.get(info.container_id)
            container.stop(timeout=5)
            container.remove()
            logger.info("Removed session container %s", info.container_name)
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.warning("Error stopping container %s: %s", info.container_name, e)

    def getContainerInfo(self, session_id: str) -> ContainerInfo | None:
        return self._containers.get(session_id)

    async def cleanupAll(self) -> None:
        """Stop all session containers on shutdown."""
        loop = asyncio.get_event_loop()
        for session_id, info in list(self._containers.items()):
            await loop.run_in_executor(None, self._stopContainer, info)
        self._containers.clear()
        self._writeTokenFile()


container_manager = ContainerManager()
