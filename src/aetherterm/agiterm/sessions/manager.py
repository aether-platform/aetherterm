"""SDK session manager — multi-tenant PTY management using shared core.

Supports skill injection: before spawning a Claude Code session, the manager
can write SKILL.md files and CLAUDE.md context into the session workspace so
that Claude Code automatically discovers and uses them.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from aetherterm.agiterm.sandbox import SandboxBackend, create_backend
from aetherterm.core.pane.layout import LayoutEngine
from aetherterm.core.pty import PTYManager, PTYSession

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
        "cmd": ["claude", "--dangerously-skip-permissions"],
        "label": "Claude Code",
        "env": {"TERM": "xterm-256color"},
    },
    "codex": {
        "cmd": ["codex", "--full-auto"],
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
    backend_type: str = "cri"
    runtime_handler: str = ""
    # Workspace panes — ordered list preserves insertion order for layout
    panes: list[Pane] = field(default_factory=list)
    # Workspace event listeners (WebSocket handlers register here)
    _workspace_listeners: list = field(default_factory=list)

    def add_workspace_listener(self, callback) -> None:
        """Register a callback(event_type, data) for workspace changes."""
        self._workspace_listeners.append(callback)

    def remove_workspace_listener(self, callback) -> None:
        """Unregister a workspace listener."""
        try:
            self._workspace_listeners.remove(callback)
        except ValueError:
            pass

    async def notify_workspace(self, event_type: str, data: dict) -> None:
        """Notify all workspace listeners of an event."""
        for cb in list(self._workspace_listeners):
            try:
                await cb(event_type, data)
            except Exception:
                pass


class SDKSessionManager:
    """Manages PTY sessions with tenant isolation.

    Each session is owned by a tenant + user pair.
    Uses the shared core PTYManager for PTY lifecycle.
    """

    def __init__(
        self,
        sandbox_backend: SandboxBackend | None = None,
        litellm_proxy_url: str = "",
    ) -> None:
        self._sessions: dict[str, SDKSession] = {}
        self._pty_manager = PTYManager()
        self._backend = sandbox_backend or create_backend()
        self._litellm_proxy_url = litellm_proxy_url or os.environ.get(
            "LITELLM_PROXY_URL", ""
        )

    # Map of tool name → env var that overrides the API base URL
    _PROXY_ENV_MAP: dict[str, str] = {
        "claude": "ANTHROPIC_BASE_URL",
        "codex": "OPENAI_BASE_URL",
        "opencode": "OPENAI_BASE_URL",
        "gemini": "GEMINI_API_BASE_URL",
    }

    def _litellm_env_for_tool(self, tool: str, tenant_id: str = "") -> dict[str, str]:
        """Return env vars to route a tool's API calls through the LiteLLM proxy.

        Returns an empty dict when no proxy is configured or the tool is not
        an AI CLI (e.g. plain bash).
        """
        if not self._litellm_proxy_url:
            return {}

        env_var = self._PROXY_ENV_MAP.get(tool)
        if not env_var:
            return {}

        env: dict[str, str] = {env_var: self._litellm_proxy_url}

        # Expose tenant/team ID so the proxy can attribute usage
        if tenant_id:
            env["LITELLM_TEAM_ID"] = tenant_id

        return env

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

    @staticmethod
    def _trust_workspace(tool: str, workspace: str) -> None:
        """Pre-trust a workspace directory for AI CLI tools.

        - Codex: Add [projects."<path>"] trust_level = "trusted" to ~/.codex/config.toml
        - Claude: Add to trustedDirectories in ~/.claude/settings.json
        """
        import json

        home = os.path.expanduser("~")

        if tool == "codex":
            config_path = os.path.join(home, ".codex", "config.toml")
            try:
                content = ""
                if os.path.exists(config_path):
                    with open(config_path) as f:
                        content = f.read()

                section = f'[projects."{workspace}"]\ntrust_level = "trusted"\n'
                if workspace not in content:
                    with open(config_path, "a") as f:
                        f.write(f"\n{section}")
                    log.debug("Codex trust added for %s", workspace)
            except OSError as e:
                log.warning("Failed to configure Codex trust: %s", e)

        elif tool == "claude":
            settings_path = os.path.join(home, ".claude", "settings.json")
            try:
                settings: dict = {}
                if os.path.exists(settings_path):
                    with open(settings_path) as f:
                        settings = json.load(f)

                trusted = settings.get("trustedDirectories", [])
                if workspace not in trusted:
                    trusted.append(workspace)
                    settings["trustedDirectories"] = trusted
                    with open(settings_path, "w") as f:
                        json.dump(settings, f, indent=2)
                    log.debug("Claude trust added for %s", workspace)
            except (OSError, json.JSONDecodeError) as e:
                log.warning("Failed to configure Claude trust: %s", e)

    def _resolve_command(self, tool: str, username: str) -> list[str]:
        """Resolve the command for a session, wrapping via CRI sandbox backend."""
        preset = TOOL_PRESETS.get(tool)
        if not preset:
            raise ValueError(f"Unknown tool: {tool}. Available: {list(TOOL_PRESETS.keys())}")

        cmd = list(preset["cmd"])
        return self._backend.wrap_command(username, cmd)

    async def create_session(
        self,
        tenant_id: str,
        user_id: str,
        tool: str = "bash",
        cols: int = 80,
        rows: int = 24,
        label: str = "",
        prompt: str = "",
        skills: list[SkillSource] | None = None,
        workspace: str = "",
        auth_token: str = "",
        api_base_url: str = "",
        runtime_handler: str = "",
    ) -> SDKSession:
        """Create a new PTY session for a tenant user.

        Lifecycle:
            1. Provision workspace directory
            2. Inject skills (SKILL.md + CLAUDE.md) into workspace
            3. Inject auth credentials as files
            4. Prepare sandbox (if sandbox=True and CRI available)
            5. Spawn PTY process via shared core PTYManager
        """
        session_id = f"sdk-{uuid.uuid4().hex[:12]}"

        # Phase 1: Host workspace (mounted as /workspace in CRI container)
        host_workspace = f"/tmp/aetherterm-workspaces/{user_id}"
        os.makedirs(host_workspace, exist_ok=True)
        if not workspace:
            workspace = "/workspace"

        # Phase 2: Inject skills (into host workspace, visible in container)
        skill_env: dict[str, str] = {}
        if skills:
            skill_env = inject_skills(host_workspace, skills)
            log.info("Injected %d skills into %s", len(skills), host_workspace)

        # Phase 3: Inject auth credentials
        creds_dir = os.path.join(host_workspace, ".agiterm", "credentials")
        os.makedirs(creds_dir, mode=0o700, exist_ok=True)
        if auth_token:
            token_path = os.path.join(creds_dir, "token")
            with open(token_path, "w") as f:
                f.write(auth_token)
            os.chmod(token_path, 0o600)
        if api_base_url:
            url_path = os.path.join(creds_dir, "api_url")
            with open(url_path, "w") as f:
                f.write(api_base_url)
            os.chmod(url_path, 0o600)

        auth_env: dict[str, str] = {
            "AGITERM_CREDENTIALS_DIR": creds_dir,
        }

        # Pre-trust workspace for AI CLI tools
        self._trust_workspace(tool, workspace)

        preset = TOOL_PRESETS.get(tool, TOOL_PRESETS["bash"])
        proxy_env = self._litellm_env_for_tool(tool, tenant_id)
        extra_env = {**preset.get("env", {}), **skill_env, **auth_env, **proxy_env}

        # Phase 4: Prepare CRI sandbox (PodSandbox + Container)
        await self._backend.prepare(
            username=user_id,
            session_id=session_id,
            image=os.environ.get("SANDBOX_IMAGE", "aetherterm-sandbox:latest"),
            env=extra_env,
            runtime_handler=runtime_handler,
        )

        cmd = self._resolve_command(tool, user_id)

        # Phase 5: Spawn PTY via shared core
        pty_session = await self._pty_manager.spawn(
            session_id=session_id,
            cmd=cmd,
            env=extra_env,
            cwd=workspace,
            cols=cols,
            rows=rows,
        )

        if not label:
            label = preset.get("label", tool)

        sdk_session = SDKSession(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            tool=tool,
            pty_session=pty_session,
            label=label,
            backend_type=self._backend.backend_type,
            runtime_handler=runtime_handler,
        )

        self._sessions[session_id] = sdk_session
        log.info(
            "Created session %s tool=%s backend=%s tenant=%s user=%s",
            session_id, tool, self._backend.backend_type, tenant_id, user_id,
        )

        # Schedule prompt injection after tool starts up
        if prompt:
            asyncio.get_event_loop().call_later(
                1.5,
                lambda: pty_session.write(prompt.encode() + b"\n"),
            )
            log.info("Scheduled prompt for session %s: %s", session_id, prompt[:80])

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

        # Kill primary PTY via shared core
        await self._pty_manager.kill(session_id)

        # Kill pane PTYs
        for pane in session.panes:
            await self._pty_manager.kill(pane.pane_id)

        # Cleanup CRI sandbox (PodSandbox + Container)
        await self._backend.cleanup(session.user_id, session_id)

        del self._sessions[session_id]
        log.info("Destroyed session %s", session_id)
        return True

    async def read_output(
        self,
        session: SDKSession,
    ) -> asyncio.Queue[bytes]:
        """Create an output queue for a session (for WebSocket streaming).

        The shared core PTYManager handles the read loop; we just subscribe.
        """
        return session.pty_session.subscribe()

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

        Spawns a new PTY process via shared core and attaches to the session.
        """
        session = self.get_session(session_id, tenant_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        preset = TOOL_PRESETS.get(tool)
        if not preset:
            raise ValueError(
                f"Unknown tool: {tool}. Available: {list(TOOL_PRESETS.keys())}"
            )

        pane_id = f"pane-{uuid.uuid4().hex[:8]}"
        cmd = list(preset["cmd"])
        extra_env = preset.get("env", {})

        pane_pty = await self._pty_manager.spawn(
            session_id=pane_id,
            cmd=cmd,
            env=extra_env,
            cols=cols,
            rows=rows,
        )

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
            pane_id, tool, role, session_id,
        )

        # Notify workspace listeners
        layout = self.get_layout(session_id, tenant_id)
        await session.notify_workspace("pane_added", {
            "pane_id": pane_id, "role": role, "tool": tool, "title": title,
        })
        await session.notify_workspace("layout", {"tree": layout})

        return pane

    async def remove_pane(
        self,
        session_id: str,
        tenant_id: str,
        pane_id: str,
    ) -> bool:
        """Remove a pane from a session and kill its PTY process."""
        session = self.get_session(session_id, tenant_id)
        if not session:
            return False

        for i, pane in enumerate(session.panes):
            if pane.pane_id == pane_id:
                await self._pty_manager.kill(pane_id)
                session.panes.pop(i)
                log.info("Removed pane %s from session=%s", pane_id, session_id)

                # Notify workspace listeners
                await session.notify_workspace("pane_removed", {"pane_id": pane_id})
                layout = self.get_layout(session_id, tenant_id)
                await session.notify_workspace("layout", {"tree": layout})

                return True

        return False

    def get_layout(
        self,
        session_id: str,
        tenant_id: str,
    ) -> dict[str, Any] | None:
        """Return the current layout as a balanced binary tree."""
        session = self.get_session(session_id, tenant_id)
        if not session:
            return None

        pane_ids = [p.pane_id for p in session.panes]
        if not pane_ids:
            return {}
        return LayoutEngine.build_balanced(pane_ids).to_dict()

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
