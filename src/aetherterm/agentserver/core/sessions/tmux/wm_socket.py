"""Unix domain socket server for tmux-like CLI access to TmuxSessionRegistry.

Protocol: JSON lines (one JSON object per line).
  Request:  {"cmd": "split", "args": {"direction": "h", "cmd": ["bash"]}}
  Response: {"ok": true, "data": {...}} or {"ok": false, "error": "..."}

Socket path: /tmp/aetherterm-wm-{uid}/default.sock
Override via WM_SOCKET environment variable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ...activity import get_session_log

if TYPE_CHECKING:
    from .session_registry import TmuxSessionRegistry

log = logging.getLogger("aetherterm.wm_socket")


def default_socket_path() -> str:
    override = os.environ.get("WM_SOCKET")
    if override:
        return override
    uid = os.getuid()
    return f"/tmp/aetherterm-wm-{uid}/default.sock"


class WmSocketServer:
    """Unix domain socket server exposing TmuxSessionRegistry operations."""

    def __init__(self, registry: TmuxSessionRegistry, socket_path: Optional[str] = None):
        self._reg = registry
        self.socket_path = socket_path or default_socket_path()
        self._server: Optional[asyncio.AbstractServer] = None
        # Default session to operate on (first created or explicit)
        self._default_session_id: str = ""

    @property
    def _session_id(self) -> str:
        """Resolve the active session ID."""
        if self._default_session_id and self._default_session_id in self._reg.sessions:
            return self._default_session_id
        if self._reg.sessions:
            return next(iter(self._reg.sessions))
        return ""

    async def start(self) -> None:
        sock_path = Path(self.socket_path)
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        if sock_path.exists():
            sock_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(sock_path)
        )
        os.chmod(str(sock_path), 0o700)
        log.info("WM socket server listening on %s", self.socket_path)

        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        sock_path = Path(self.socket_path)
        if sock_path.exists():
            sock_path.unlink()
        log.info("WM socket server stopped")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    req = json.loads(line.decode("utf-8").strip())
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    resp = {"ok": False, "error": f"invalid JSON: {e}"}
                    writer.write((json.dumps(resp) + "\n").encode())
                    await writer.drain()
                    continue

                resp = await self._dispatch(req)
                self._log_activity(req, resp)
                writer.write((json.dumps(resp) + "\n").encode())
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(self, req: dict) -> dict:
        cmd = req.get("cmd", "")
        args = req.get("args", {})

        try:
            sid = self._session_id
            if not sid and cmd not in ("list-windows", "list-panes"):
                # Auto-create a session
                session = self._reg.create_session(name="default")
                sid = session.session_id
                self._default_session_id = sid

            session = self._reg.get_session(sid) if sid else None

            if cmd == "list-windows":
                if not session:
                    return {"ok": True, "data": []}
                windows = []
                for w in session.windows.values():
                    windows.append({
                        "window_id": w.window_id,
                        "title": w.name,
                        "pane_count": len(w.panes),
                        "active": w.window_id == session.active_window_id,
                    })
                return {"ok": True, "data": windows}

            elif cmd == "list-panes":
                if not session:
                    return {"ok": True, "data": []}
                wid = args.get("window_id")
                panes = []
                for w in session.windows.values():
                    if wid and w.window_id != wid:
                        continue
                    for p in w.panes.values():
                        panes.append({
                            "pane_id": p.pane_id,
                            "window_id": w.window_id,
                            "title": p.title or p.role,
                            "role": p.role,
                            "status": p.status.value,
                            "focused": p.pane_id == w.active_pane_id,
                        })
                return {"ok": True, "data": panes}

            elif cmd == "new-window":
                title = args.get("title", "Shell")
                cmd_list = args.get("cmd")
                if isinstance(cmd_list, str) and cmd_list:
                    cmd_list = ["bash", "-c", cmd_list]
                elif not cmd_list:
                    cmd_list = None
                window = await self._reg.create_window(
                    sid, name=title, cmd=cmd_list, role=args.get("role", ""),
                )
                if window is None:
                    return {"ok": False, "error": "create window failed"}
                return {"ok": True, "data": {
                    "window_id": window.window_id,
                    "title": window.name,
                    "pane_count": len(window.panes),
                }}

            elif cmd == "close-window":
                wid = args.get("window_id", "")
                if not wid:
                    return {"ok": False, "error": "window_id required"}
                ok = await self._reg.close_window(sid, wid)
                return {"ok": ok, "error": None if ok else "window not found"}

            elif cmd == "split":
                wid = args.get("window_id")
                if not wid and session:
                    wid = session.active_window_id
                if not wid:
                    window = await self._reg.create_window(sid, name="Shell")
                    if window:
                        wid = window.window_id

                target_pane = args.get("target_pane", "")
                direction = args.get("direction", "h")
                cmd_list = args.get("cmd")
                if isinstance(cmd_list, str) and cmd_list:
                    cmd_list = ["bash", "-c", cmd_list]
                elif not cmd_list:
                    cmd_list = None

                pane = await self._reg.split_pane(
                    sid, wid,
                    target_pane_id=target_pane,
                    direction=direction,
                    cmd=cmd_list,
                    role=args.get("role", ""),
                )
                if pane is None:
                    return {"ok": False, "error": "split failed"}
                return {"ok": True, "data": {
                    "pane_id": pane.pane_id,
                    "window_id": wid,
                    "role": pane.role,
                }}

            elif cmd == "close-pane":
                pid = args.get("pane_id", "")
                if not pid:
                    return {"ok": False, "error": "pane_id required"}
                loc = self._reg.find_pane_location(pid)
                if not loc:
                    return {"ok": False, "error": f"pane not found: {pid}"}
                ok = await self._reg.close_pane(loc[0], loc[1], pid)
                return {"ok": ok, "error": None if ok else "close failed"}

            elif cmd == "focus":
                pid = args.get("pane_id", "")
                if not pid:
                    return {"ok": False, "error": "pane_id required"}
                loc = self._reg.find_pane_location(pid)
                if not loc:
                    return {"ok": False, "error": f"pane not found: {pid}"}
                ok = self._reg.focus_pane(loc[0], loc[1], pid)
                return {"ok": ok, "error": None if ok else "focus failed"}

            elif cmd == "send-keys":
                return self._send_keys(args)

            elif cmd == "capture-pane":
                return self._capture_pane(args)

            elif cmd == "spawn-agent":
                return await self._spawn_agent(sid, session, args)

            else:
                return {"ok": False, "error": f"unknown command: {cmd}"}

        except Exception as e:
            log.exception("Socket command %s failed", cmd)
            return {"ok": False, "error": str(e)}

    async def _spawn_agent(self, sid: str, session, args: dict) -> dict:
        """Spawn a NATS-connected agent in a new window.

        Args (in args dict):
            role: Agent role (coder, reviewer, tester, etc.)
            agent_id: Optional, auto-generated if not set
            nats_url: NATS server URL (default from env)
            claude: Use Claude CLI instead of agentshell
            model: Claude model override
            workspace: Working directory for the agent
            cmd: Custom command override
        """
        import shutil
        import sys
        import uuid

        role = args.get("role", "shell")
        agent_id = args.get("agent_id") or f"{role}-{uuid.uuid4().hex[:6]}"
        nats_url = args.get(
            "nats_url", os.environ.get("NATS_URL", "nats://localhost:4222")
        )
        use_claude = args.get("claude", False)
        model = args.get("model")
        workspace = args.get("workspace")
        custom_cmd = args.get("cmd")

        # Build command
        if custom_cmd:
            shell_cmd = custom_cmd
        elif use_claude:
            claude_path = shutil.which("claude") or "claude"
            shell_cmd = (
                f"{claude_path} --dangerously-skip-permissions --teammate-mode tmux"
            )
            if model:
                shell_cmd += f" --model {model}"
        else:
            shell_cmd = (
                f"{sys.executable} -m aetherterm.agentshell.main "
                f"--agent-id {agent_id} --role {role} --nats-url {nats_url}"
            )
            if workspace:
                shell_cmd += f" --workspace {workspace}"

        title = f"{role}:{agent_id}"
        cmd_list = ["bash", "-c", shell_cmd]

        window = await self._reg.create_window(
            sid, name=title, cmd=cmd_list, role=role,
        )
        if window is None:
            return {"ok": False, "error": "failed to create window for agent"}

        pane = next(iter(window.panes.values()), None)
        return {"ok": True, "data": {
            "agent_id": agent_id,
            "role": role,
            "window_id": window.window_id,
            "pane_id": pane.pane_id if pane else "",
            "session_id": sid,
            "nats_url": nats_url,
            "cmd": shell_cmd,
        }}

    def _send_keys(self, args: dict) -> dict:
        """Send keystrokes to a pane's PTY."""
        keys = args.get("keys", "")
        if not keys:
            return {"ok": False, "error": "keys required"}

        pane_id = args.get("pane_id")

        if pane_id:
            loc = self._reg.find_pane_location(pane_id)
            if not loc:
                return {"ok": False, "error": f"pane not found: {pane_id}"}
            s_id, w_id = loc
        else:
            s_id = self._session_id
            session = self._reg.get_session(s_id)
            if not session:
                return {"ok": False, "error": "no session"}
            w_id = session.active_window_id
            window = session.windows.get(w_id)
            if not window:
                return {"ok": False, "error": "no active window"}
            pane_id = window.active_pane_id

        if isinstance(keys, str):
            keys = keys.replace("\n", "\r")
        data = keys.encode() if isinstance(keys, str) else keys

        ok = self._reg.write_to_pane(s_id, w_id, pane_id, data)
        if not ok:
            return {"ok": False, "error": "write failed"}
        return {"ok": True}

    def _capture_pane(self, args: dict) -> dict:
        """Capture terminal output from a pane's history buffer."""
        pane_id = args.get("pane_id")
        max_lines = args.get("lines", 50)

        if pane_id:
            loc = self._reg.find_pane_location(pane_id)
            if not loc:
                return {"ok": False, "error": f"pane not found: {pane_id}"}
            s_id, w_id = loc
        else:
            s_id = self._session_id
            session = self._reg.get_session(s_id)
            if not session:
                return {"ok": False, "error": "no session"}
            w_id = session.active_window_id
            window = session.windows.get(w_id)
            if not window:
                return {"ok": False, "error": "no active window"}
            pane_id = window.active_pane_id

        session = self._reg.get_session(s_id)
        window = session.windows.get(w_id) if session else None
        pane = window.panes.get(pane_id) if window else None

        if not pane:
            return {"ok": False, "error": "pane not found"}

        text = bytes(pane.history).decode("utf-8", errors="replace")
        # Strip ANSI escape codes
        text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
        text = re.sub(r'\x1b\][^\x07]*\x07', '', text)

        lines = text.splitlines()
        if max_lines and len(lines) > max_lines:
            lines = lines[-max_lines:]

        content = "\n".join(lines)
        return {"ok": True, "data": {
            "pane_id": pane_id,
            "content": content,
            "lines": len(lines),
        }}

    def _log_activity(self, req: dict, resp: dict) -> None:
        """Log socket commands as activity events for timeline."""
        try:
            activity = get_session_log("default")
        except Exception:
            return

        cmd = req.get("cmd", "")
        args = req.get("args", {})
        if not resp.get("ok"):
            return

        if cmd == "new-window":
            activity.add("create", source="orchestrator", target=args.get("title", "Shell"),
                          detail=f"Created window: {args.get('title', 'Shell')}")
        elif cmd == "split":
            activity.add("split", source="orchestrator", target=args.get("role", "shell"),
                          detail=f"Split pane ({args.get('direction', 'h')})")
        elif cmd == "send-keys":
            keys = args.get("keys", "")
            preview = keys[:80] + ("..." if len(keys) > 80 else "")
            preview = preview.replace("\r", " ").replace("\n", " ")
            activity.add("send_keys", source="orchestrator",
                          target=args.get("pane_id", "active"), detail=preview)
        elif cmd == "close-pane":
            activity.add("close", source="orchestrator",
                          target=args.get("pane_id", ""), detail="Closed pane")
        elif cmd == "spawn-agent":
            activity.add("spawn", source="orchestrator",
                          target=args.get("role", "agent"),
                          detail=f"Spawned agent: {args.get('agent_id', args.get('role', ''))}")
