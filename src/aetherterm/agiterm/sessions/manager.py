"""SDK session manager — thin wrapper around PTYSessionManager for multi-tenant use."""

import asyncio
import logging
import os
import pty
import shutil
import uuid
from dataclasses import dataclass, field
from typing import Optional

from aetherterm.agentserver.core.sessions.manager import PTYSession, PTYSessionManager

log = logging.getLogger("agiterm.sessions")


# Supported AI CLI tool presets
TOOL_PRESETS: dict[str, dict] = {
    "bash": {
        "cmd": ["/bin/bash"],
        "label": "Bash Shell",
        "env": {},
    },
    "claude": {
        "cmd": ["claude"],
        "label": "Claude Code",
        "env": {"TERM": "xterm-256color"},
    },
    "codex": {
        "cmd": ["codex"],
        "label": "OpenAI Codex CLI",
        "env": {"TERM": "xterm-256color"},
    },
    "opencode": {
        "cmd": ["opencode"],
        "label": "OpenCode",
        "env": {"TERM": "xterm-256color"},
    },
    "gemini": {
        "cmd": ["gemini"],
        "label": "Gemini CLI",
        "env": {"TERM": "xterm-256color"},
    },
}


@dataclass
class SDKSession:
    """An SDK terminal session scoped to a tenant."""

    session_id: str
    tenant_id: str
    user_id: str
    tool: str
    pty_session: PTYSession
    created_at: float = field(default_factory=lambda: __import__("time").time())
    label: str = ""


class SDKSessionManager:
    """Manages PTY sessions with tenant isolation.

    Each session is owned by a tenant + user pair.
    Reuses the core PTYSession for actual PTY operations.
    """

    def __init__(self, sandbox_image: str = "") -> None:
        self._sessions: dict[str, SDKSession] = {}
        self._pty_manager = PTYSessionManager()
        self._sandbox_image = sandbox_image  # Docker image for sandboxed sessions

    @staticmethod
    def available_tools() -> dict[str, str]:
        """Return available tool presets with availability status."""
        result = {}
        for name, preset in TOOL_PRESETS.items():
            binary = preset["cmd"][0]
            found = shutil.which(binary) is not None
            result[name] = {
                "label": preset["label"],
                "available": found,
                "binary": binary,
            }
        return result

    def _build_command(self, tool: str, sandbox: bool) -> list[str]:
        """Build the command to execute for a session."""
        preset = TOOL_PRESETS.get(tool)
        if not preset:
            raise ValueError(f"Unknown tool: {tool}. Available: {list(TOOL_PRESETS.keys())}")

        cmd = list(preset["cmd"])

        if sandbox and self._sandbox_image:
            # Wrap in Docker for isolation
            docker_cmd = [
                "docker", "run", "--rm", "-it",
                "--network=none",  # No network access in sandbox
                "--memory=512m",
                "--cpus=1",
                "--pids-limit=100",
                f"--name=agi-sandbox-{uuid.uuid4().hex[:8]}",
                self._sandbox_image,
            ] + cmd
            return docker_cmd

        return cmd

    async def create_session(
        self,
        tenant_id: str,
        user_id: str,
        tool: str = "bash",
        sandbox: bool = False,
        cols: int = 80,
        rows: int = 24,
        label: str = "",
    ) -> SDKSession:
        """Create a new PTY session for a tenant user.

        Args:
            tool: One of "bash", "claude", "codex", "opencode", "gemini"
            sandbox: If True, run inside a Docker container for isolation
        """
        session_id = f"sdk-{uuid.uuid4().hex[:12]}"
        cmd = self._build_command(tool, sandbox)
        preset = TOOL_PRESETS.get(tool, TOOL_PRESETS["bash"])
        extra_env = preset.get("env", {})

        child_pid, master_fd = pty.fork()

        if child_pid == 0:
            # Child process
            for k, v in extra_env.items():
                os.environ[k] = v
            os.environ.setdefault("TERM", "xterm-256color")
            os.execvp(cmd[0], cmd)

        # Parent process
        pty_session = PTYSession(
            session_id=session_id,
            master_fd=master_fd,
            pid=child_pid,
        )
        pty_session.resize(cols, rows)

        if not label:
            label = preset.get("label", tool)

        sdk_session = SDKSession(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            tool=tool,
            pty_session=pty_session,
            label=label,
        )

        self._sessions[session_id] = sdk_session
        log.info(
            "Created session %s tool=%s sandbox=%s tenant=%s user=%s",
            session_id, tool, sandbox, tenant_id, user_id,
        )
        return sdk_session

    def get_session(
        self,
        session_id: str,
        tenant_id: str,
    ) -> Optional[SDKSession]:
        """Get a session, enforcing tenant isolation."""
        session = self._sessions.get(session_id)
        if session and session.tenant_id == tenant_id:
            return session
        return None

    def list_sessions(self, tenant_id: str) -> list[SDKSession]:
        """List all sessions for a tenant."""
        return [
            s for s in self._sessions.values()
            if s.tenant_id == tenant_id
        ]

    async def destroy_session(
        self,
        session_id: str,
        tenant_id: str,
    ) -> bool:
        """Destroy a session, enforcing tenant isolation."""
        session = self.get_session(session_id, tenant_id)
        if not session:
            return False

        try:
            os.kill(session.pty_session.pid, 9)
        except OSError:
            pass

        try:
            os.close(session.pty_session.master_fd)
        except OSError:
            pass

        del self._sessions[session_id]
        log.info("Destroyed session %s", session_id)
        return True

    async def read_output(
        self,
        session: SDKSession,
    ) -> asyncio.Queue[bytes]:
        """Create an output queue for a session (for WebSocket streaming)."""
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        session.pty_session.clients.add(queue)

        loop = asyncio.get_event_loop()
        loop.add_reader(
            session.pty_session.master_fd,
            self._on_pty_output,
            session.pty_session,
        )

        return queue

    def _on_pty_output(self, pty_session: PTYSession) -> None:
        """Callback when PTY has output ready."""
        try:
            data = os.read(pty_session.master_fd, 65536)
            if data:
                pty_session.history.extend(data)
                for queue in pty_session.clients:
                    queue.put_nowait(data)
        except OSError:
            pass
