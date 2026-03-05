import asyncio
import logging
from typing import Any, Dict, Optional

from .manager import PTYSessionManager

log = logging.getLogger("aetherterm.agent_session")


class AgentSessionManager:
    """Tracks remote agents and their control sessions.

    Bridges agent control messages to PTYSessionManager.
    """

    def __init__(self, pty_manager: PTYSessionManager):
        self.pty_manager = pty_manager
        self.agents: Dict[str, Any] = {}  # agent_id -> metadata

    async def handle_agent_message(
        self, agent_id: str, message: Dict[str, Any], send_callback: Optional[Any] = None
    ) -> None:
        """Processes control messages from an agent.
        Matches the AgentMessage protocol from common.agent_protocol.
        """
        msg_type = message.get("type") or message.get("message_type")
        payload = message.get("payload") or message

        log.debug(f"Agent {agent_id} sent message: {msg_type}")

        if msg_type == "command_execute":
            # Direct command execution request
            cmd = payload.get("command")
            pty_id = payload.get("pty_id", "default")
            session = self.pty_manager.sessions.get(pty_id)
            if session:
                log.info(f"Agent {agent_id} executing command on {pty_id}: {cmd}")
                session.write(f"{cmd}\n".encode())

        elif msg_type == "terminal_input":
            # Direct character streaming
            data = payload.get("data")
            pty_id = payload.get("pty_id", "default")
            session = self.pty_manager.sessions.get(pty_id)
            if session:
                session.write(data.encode("utf-8"))

        elif msg_type in ("pane_resize", "pty_resize"):
            pty_id = payload.get("pane_id") or payload.get("pty_id")
            session = self.pty_manager.sessions.get(pty_id)
            if session:
                cols = payload.get("cols", 80)
                rows = payload.get("rows", 24)
                session.resize(cols, rows)

        elif msg_type in ("pane_create", "pty_create"):
            pty_id = payload.get("pty_id") or payload.get("pane_id")
            log.info(f"Agent {agent_id} creating new PTY session: {pty_id}")
            self.pty_manager.create_session(pty_id)

        elif msg_type == "observe_pty":
            pty_id = payload.get("pty_id")
            session = self.pty_manager.sessions.get(pty_id)
            if session and send_callback:
                log.info(f"Agent {agent_id} observing PTY {pty_id}")
                queue = asyncio.Queue()
                session.clients.add(queue)

                async def forward_output() -> None:
                    try:
                        while True:
                            output = await queue.get()
                            if output is None:
                                break
                            await send_callback(
                                {
                                    "type": "terminal_output",
                                    "pty_id": pty_id,
                                    "data": output.decode("utf-8", errors="replace"),
                                }
                            )
                    except Exception:
                        pass
                    finally:
                        session.clients.remove(queue)

                # Store task to avoid GC
                task = asyncio.create_task(forward_output())
                task._agent_id = agent_id

        elif msg_type == "list_sessions":
            if send_callback:
                sessions = [
                    {"id": s.id, "pid": s.pid, "active_clients": len(s.clients)}
                    for s in self.pty_manager.sessions.values()
                ]
                await send_callback({"type": "session_list", "sessions": sessions})
