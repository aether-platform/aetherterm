"""SDK session manager — thin wrapper around PTYSessionManager for multi-tenant use.

Supports skill injection: before spawning a Claude Code session, the manager
can write SKILL.md files and CLAUDE.md context into the session workspace so
that Claude Code automatically discovers and uses them.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pty
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from aetherterm.agentserver.core.sessions.manager import PTYSession, PTYSessionManager

log = logging.getLogger("agiterm.sessions")


# ---------------------------------------------------------------------------
# Skill injection
# ---------------------------------------------------------------------------

@dataclass
class SkillSource:
    """A skill package to inject into a session workspace.

    Attributes:
        provider: Skill provider name (e.g. "secretary")
        skill_dir: Path to directory containing SKILL.md (and optional references/)
        context: Extra text to append to the session's CLAUDE.md
        env: Environment variables to set for the session process
    """

    provider: str
    skill_dir: str
    context: str = ""
    env: dict[str, str] = field(default_factory=dict)


def inject_skills(workspace: str, skills: list[SkillSource]) -> dict[str, str]:
    """Inject skill files and context into a workspace directory.

    For each skill:
      1. Copies SKILL.md (and siblings) to {workspace}/.claude/agents/skills/{provider}/
      2. Appends context to {workspace}/CLAUDE.md

    Returns merged environment variables from all skills.
    """
    env: dict[str, str] = {}
    ws = Path(workspace)

    for source in skills:
        # Copy SKILL.md and siblings
        dest = ws / ".claude" / "agents" / "skills" / source.provider
        dest.mkdir(parents=True, exist_ok=True)

        src = Path(source.skill_dir)
        if src.is_dir():
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, dest / f.name)
            log.info("Injected skill: %s -> %s", source.provider, dest)
        elif src.is_file():
            shutil.copy2(src, dest / "SKILL.md")
            log.info("Injected skill file: %s -> %s/SKILL.md", source.provider, dest)

        # Append context to CLAUDE.md
        if source.context:
            claude_md = ws / "CLAUDE.md"
            existing = claude_md.read_text() if claude_md.exists() else ""
            with open(claude_md, "w") as f:
                if existing:
                    f.write(existing.rstrip() + "\n\n")
                f.write(source.context)
            log.info("Injected context into CLAUDE.md (%d chars)", len(source.context))

        env.update(source.env)

    return env


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


# ---------------------------------------------------------------------------
# Layout tree helpers
# ---------------------------------------------------------------------------

def _build_balanced_layout(pane_ids: list[str], direction: str = "hsplit") -> dict[str, Any]:
    """Build a balanced binary tree layout from a list of pane IDs.

    The tree alternates between hsplit and vsplit at each depth level to
    produce a tiled layout similar to tmux's balanced-tiling.

    Returns a dict representing the tree node:
      - Leaf:     {"type": "leaf", "pane_id": "..."}
      - Internal: {"type": "hsplit"|"vsplit", "children": [left, right]}
    """
    if not pane_ids:
        return {}
    if len(pane_ids) == 1:
        return {"type": "leaf", "pane_id": pane_ids[0]}

    mid = len(pane_ids) // 2
    next_dir = "vsplit" if direction == "hsplit" else "hsplit"
    return {
        "type": direction,
        "children": [
            _build_balanced_layout(pane_ids[:mid], next_dir),
            _build_balanced_layout(pane_ids[mid:], next_dir),
        ],
    }


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Pane:
    """A single pane inside a workspace session."""

    pane_id: str
    tool: str
    role: str
    title: str
    pty_session: PTYSession
    created_at: float = field(default_factory=lambda: __import__("time").time())


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
    # Workspace panes — ordered list preserves insertion order for layout
    panes: list[Pane] = field(default_factory=list)


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
        skills: list[SkillSource] | None = None,
        workspace: str = "",
        auth_token: str = "",
        api_base_url: str = "",
    ) -> SDKSession:
        """Create a new PTY session for a tenant user.

        Args:
            tool: One of "bash", "claude", "codex", "opencode", "gemini"
            sandbox: If True, run inside a Docker container for isolation
            skills: Skill packages to inject before starting the session
            workspace: Working directory for the session (auto-created if empty)
            auth_token: OIDC Bearer token (LogTo) for API authentication
            api_base_url: Secretary.IO API base URL for skill API calls

        Lifecycle:
            1. Provision workspace directory
            2. Inject skills (SKILL.md + CLAUDE.md) into workspace
            3. Inject auth credentials as environment variables
            4. Spawn PTY process with tool command
        """
        session_id = f"sdk-{uuid.uuid4().hex[:12]}"

        # Phase 1: Provision workspace
        if not workspace:
            workspace = os.path.join("/tmp", "agiterm-sessions", session_id)
        os.makedirs(workspace, exist_ok=True)

        # Phase 2: Inject skills
        skill_env: dict[str, str] = {}
        if skills:
            skill_env = inject_skills(workspace, skills)
            log.info("Injected %d skills into %s", len(skills), workspace)

        # Phase 3: Inject auth credentials
        auth_env: dict[str, str] = {}
        if auth_token:
            auth_env["SECRETARY_AUTH_TOKEN"] = auth_token
        if api_base_url:
            auth_env["SECRETARY_API_URL"] = api_base_url

        cmd = self._build_command(tool, sandbox)
        preset = TOOL_PRESETS.get(tool, TOOL_PRESETS["bash"])
        extra_env = {**preset.get("env", {}), **skill_env, **auth_env}

        # Phase 4: Spawn PTY
        child_pid, master_fd = pty.fork()

        if child_pid == 0:
            # Child process
            os.chdir(workspace)
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

    # ------------------------------------------------------------------
    # Pane management (workspace multi-pane support)
    # ------------------------------------------------------------------

    async def add_pane(
        self,
        session_id: str,
        tenant_id: str,
        tool: str = "bash",
        role: str = "",
        cols: int = 80,
        rows: int = 24,
    ) -> Pane:
        """Add a new pane to an existing session.

        Spawns a new PTY process and attaches it to the session's pane list.
        The layout is automatically rebalanced.

        Raises ValueError if session not found or tool unknown.
        """
        session = self.get_session(session_id, tenant_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        preset = TOOL_PRESETS.get(tool)
        if not preset:
            raise ValueError(
                f"Unknown tool: {tool}. Available: {list(TOOL_PRESETS.keys())}"
            )

        cmd = list(preset["cmd"])
        extra_env = preset.get("env", {})

        pane_id = f"pane-{uuid.uuid4().hex[:8]}"

        child_pid, master_fd = pty.fork()

        if child_pid == 0:
            # Child process
            for k, v in extra_env.items():
                os.environ[k] = v
            os.environ.setdefault("TERM", "xterm-256color")
            os.execvp(cmd[0], cmd)

        # Parent process
        pane_pty = PTYSession(
            session_id=pane_id,
            master_fd=master_fd,
            pid=child_pid,
        )
        pane_pty.resize(cols, rows)

        title = role if role else preset.get("label", tool)

        pane = Pane(
            pane_id=pane_id,
            tool=tool,
            role=role,
            title=title,
            pty_session=pane_pty,
        )

        session.panes.append(pane)
        log.info(
            "Added pane %s tool=%s role=%s to session=%s",
            pane_id,
            tool,
            role,
            session_id,
        )
        return pane

    async def remove_pane(
        self,
        session_id: str,
        tenant_id: str,
        pane_id: str,
    ) -> bool:
        """Remove a pane from a session and kill its PTY process.

        Returns True if the pane was found and removed, False otherwise.
        """
        session = self.get_session(session_id, tenant_id)
        if not session:
            return False

        for i, pane in enumerate(session.panes):
            if pane.pane_id == pane_id:
                # Kill the PTY
                try:
                    os.kill(pane.pty_session.pid, 9)
                except OSError:
                    pass
                try:
                    os.close(pane.pty_session.master_fd)
                except OSError:
                    pass

                session.panes.pop(i)
                log.info("Removed pane %s from session=%s", pane_id, session_id)
                return True

        return False

    def get_layout(
        self,
        session_id: str,
        tenant_id: str,
    ) -> dict[str, Any] | None:
        """Return the current layout as a balanced binary tree.

        Returns None if the session is not found.
        Returns an empty dict if there are no panes.
        """
        session = self.get_session(session_id, tenant_id)
        if not session:
            return None

        pane_ids = [p.pane_id for p in session.panes]
        return _build_balanced_layout(pane_ids)

    def get_panes(
        self,
        session_id: str,
        tenant_id: str,
    ) -> list[Pane]:
        """Return all panes for a session (empty list if session not found)."""
        session = self.get_session(session_id, tenant_id)
        if not session:
            return []
        return list(session.panes)

    def get_pane(
        self,
        session_id: str,
        tenant_id: str,
        pane_id: str,
    ) -> Pane | None:
        """Look up a single pane by ID within a session."""
        session = self.get_session(session_id, tenant_id)
        if not session:
            return None
        for pane in session.panes:
            if pane.pane_id == pane_id:
                return pane
        return None
