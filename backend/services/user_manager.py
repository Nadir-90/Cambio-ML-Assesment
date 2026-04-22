import os
import re
import asyncio
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_CU_HOME = Path(os.environ.get("HOME", "/home/computeruse"))
TINT2_SRC = _CU_HOME / ".tint2" / "tint2rc"
TINT2_APPS_SRC = _CU_HOME / ".tint2" / "applications"

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")
SYSTEM_USERS = frozenset(
    {
        "root",
        "daemon",
        "bin",
        "sys",
        "sync",
        "games",
        "man",
        "lp",
        "mail",
        "news",
        "uucp",
        "proxy",
        "www-data",
        "backup",
        "list",
        "irc",
        "gnats",
        "nobody",
        "systemd-network",
        "systemd-resolve",
        "systemd-timesync",
        "messagebus",
        "syslog",
        "computeruse",
        "_apt",
        "pulse",
        "uuidd",
    }
)


@dataclass
class UserInfo:
    """Tracks a dynamically created Linux user shared across sessions."""

    username: str
    home_dir: str
    session_ids: set[str] = field(default_factory=set)


class UserManager:
    """Manages Linux users for session environment isolation."""

    def __init__(self) -> None:
        """Initialize the user registry and async lock."""
        self._users: dict[str, UserInfo] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def validateUsername(username: str) -> str:
        """Validate username and return it, or raise ValueError."""
        if not USERNAME_RE.match(username):
            raise ValueError(
                "Username must be 3-32 characters, start with a lowercase "
                "letter, and contain only lowercase letters, digits, "
                "underscores, or hyphens."
            )
        if username in SYSTEM_USERS:
            raise ValueError(f"Username '{username}' is reserved.")
        return username

    async def createUser(self, session_id: str, username: str) -> UserInfo:
        """Create or reuse a Linux user for the given session, setting up home dir and sudo access."""
        self.validateUsername(username)

        async with self._lock:
            if username in self._users:
                self._users[username].session_ids.add(session_id)
                logger.info(
                    "Session %s linked to existing user %s",
                    session_id,
                    username,
                )
                return self._users[username]

            home_dir = f"/home/{username}"
            loop = asyncio.get_running_loop()

            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "sudo",
                        "useradd",
                        "-m",
                        "-s",
                        "/bin/bash",
                        "-G",
                        "computeruse",
                        username,
                    ],
                    capture_output=True,
                ),
            )

            sudoers_line = (
                f"{username} ALL=(ALL) NOPASSWD: "
                "/usr/bin/apt-get, /usr/bin/apt, /usr/bin/dpkg\n"
            )
            sudoers_path = f"/etc/sudoers.d/{username}"
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["sudo", "tee", sudoers_path],
                    input=sudoers_line.encode(),
                    capture_output=True,
                ),
            )
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["sudo", "chmod", "440", sudoers_path],
                    capture_output=True,
                ),
            )

            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["sudo", "chmod", "770", home_dir],
                    capture_output=True,
                ),
            )

            tint2_dest = Path(home_dir) / ".tint2"
            apps_dest = tint2_dest / "applications"
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["sudo", "mkdir", "-p", str(apps_dest)],
                    capture_output=True,
                ),
            )
            if TINT2_APPS_SRC.is_dir():
                await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [
                            "sudo",
                            "bash",
                            "-c",
                            f"cp {TINT2_APPS_SRC}/*.desktop {apps_dest}/ "
                            "2>/dev/null || true",
                        ],
                        capture_output=True,
                    ),
                )
            if TINT2_SRC.exists():
                cu_home_str = str(_CU_HOME)
                await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [
                            "sudo",
                            "bash",
                            "-c",
                            f"sed 's|{cu_home_str}|{home_dir}|g' "
                            f"'{TINT2_SRC}' > '{tint2_dest}/tint2rc'",
                        ],
                        capture_output=True,
                    ),
                )

            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["sudo", "chown", "-R", f"{username}:{username}", home_dir],
                    capture_output=True,
                ),
            )
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["sudo", "chgrp", "computeruse", home_dir],
                    capture_output=True,
                ),
            )

            info = UserInfo(
                username=username,
                home_dir=home_dir,
                session_ids={session_id},
            )
            self._users[username] = info
            logger.info(
                "User %s created for session %s (home: %s)",
                username,
                session_id,
                home_dir,
            )
            return info

    async def deleteUser(self, session_id: str, username: str) -> None:
        """Unlink session from username; remove the Linux user when no sessions remain."""
        async with self._lock:
            info = self._users.get(username)
            if not info:
                return
            info.session_ids.discard(session_id)
            if not info.session_ids:
                del self._users[username]
                await self.removeSystemUser(username)
                logger.info(
                    "User %s deleted (last session %s removed)",
                    username,
                    session_id,
                )
            else:
                logger.info(
                    "Session %s unlinked from user %s (%d sessions remain)",
                    session_id,
                    username,
                    len(info.session_ids),
                )

    def getUserInfo(self, session_id: str) -> UserInfo | None:
        """Return user info for the given session, or None."""
        for info in self._users.values():
            if session_id in info.session_ids:
                return info
        return None

    def getUserByName(self, username: str) -> UserInfo | None:
        """Return user info by username."""
        return self._users.get(username)

    async def cleanupAll(self) -> None:
        """Delete all managed users (shutdown hook)."""
        async with self._lock:
            for info in self._users.values():
                await self.removeSystemUser(info.username)
            self._users.clear()
            logger.info("All session users cleaned up")

    @staticmethod
    async def removeSystemUser(username: str) -> None:
        """Remove a Linux user, their home directory, and sudoers entry."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["sudo", "userdel", "-r", username],
                capture_output=True,
            ),
        )
        sudoers_path = f"/etc/sudoers.d/{username}"
        try:
            os.remove(sudoers_path)
        except OSError:
            pass


user_manager = UserManager()
