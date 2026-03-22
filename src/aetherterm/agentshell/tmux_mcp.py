"""tmux-mcp — MCP server providing tmux-compatible agent messaging.

Runs as a stdio MCP server that bridges MCP tool calls to NATS messaging.
Agents (codex, gemini, aider, etc.) can use these tools to communicate with
other agents in the tmux workspace without needing native NATS support.

This is the MCP counterpart to tmux-shim: while tmux-shim translates tmux CLI
commands for Claude's --teammate-mode, tmux-mcp provides MCP tools for agents
that support MCP but not tmux commands.

Usage (stdio mode, typically launched by AgentShell):
    python -m aetherterm.agentshell.tmux_mcp \
        --agent-id coder-1 --nats-url nats://localhost:4222

MCP tools provided:
    - send_message: Send a message to another agent (tmux send-keys equivalent)
    - list_agents: List active agents (tmux list-panes equivalent)
    - report_result: Report task completion back to requester
    - get_messages: Check for pending messages
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import deque

from ..common.agent_protocol import AgentMessage, MessageBuilder, MessageType

logger = logging.getLogger("tmux_mcp")

# Max pending messages to buffer
_MAX_PENDING = 50


class NATSMCPBridge:
    """Async bridge between MCP tool calls and NATS."""

    def __init__(self, agent_id: str, nats_url: str):
        self.agent_id = agent_id
        self.nats_url = nats_url
        self.nc = None
        self._pending_messages: deque[dict] = deque(maxlen=_MAX_PENDING)
        self._known_agents: dict[str, dict] = {}  # agent_id → {role, last_seen}

    async def connect(self) -> None:
        import nats as nats_lib

        self.nc = await nats_lib.connect(
            servers=self.nats_url,
            max_reconnect_attempts=5,
            reconnect_time_wait=2,
            name=f"mcp-{self.agent_id}",
        )

        # Subscribe to incoming messages for this agent
        await self.nc.subscribe(
            f"agent.{self.agent_id}.inbox", cb=self._on_message
        )
        await self.nc.subscribe("agent.broadcast", cb=self._on_broadcast)

        # Subscribe to discovery to track agents
        await self.nc.subscribe("agent.discovery", cb=self._on_discovery)
        await self.nc.subscribe("agent.heartbeat", cb=self._on_heartbeat)

        # Register self
        reg = MessageBuilder.register(self.agent_id, "mcp-bridge")
        await self.nc.publish("agent.discovery", reg.encode())

        logger.info("NATS MCP bridge connected: %s", self.nats_url)

    async def close(self) -> None:
        if self.nc and self.nc.is_connected:
            try:
                await self.nc.drain()
            except Exception:
                pass

    async def _on_message(self, msg) -> None:
        try:
            data = json.loads(msg.data.decode("utf-8"))
            self._pending_messages.append(data)
        except Exception:
            pass

    async def _on_broadcast(self, msg) -> None:
        try:
            data = json.loads(msg.data.decode("utf-8"))
            if data.get("from_agent") != self.agent_id:
                self._pending_messages.append(data)
        except Exception:
            pass

    async def _on_discovery(self, msg) -> None:
        try:
            data = json.loads(msg.data.decode("utf-8"))
            mt = data.get("message_type", "")
            payload = data.get("payload", {})
            aid = payload.get("agent_id", data.get("from_agent", ""))
            if mt == "agent_register" and aid:
                self._known_agents[aid] = {
                    "role": payload.get("role", "unknown"),
                    "last_seen": time.time(),
                }
            elif mt == "agent_unregister" and aid:
                self._known_agents.pop(aid, None)
        except Exception:
            pass

    async def _on_heartbeat(self, msg) -> None:
        try:
            data = json.loads(msg.data.decode("utf-8"))
            aid = data.get("payload", {}).get("agent_id", data.get("from_agent", ""))
            if aid and aid in self._known_agents:
                self._known_agents[aid]["last_seen"] = time.time()
        except Exception:
            pass

    async def send_message(
        self, to_agent: str, content: str, message_type: str = "agent_dm"
    ) -> dict:
        if not self.nc or not self.nc.is_connected:
            return {"success": False, "error": "Not connected to NATS"}

        if message_type == "agent_broadcast":
            msg = MessageBuilder.send_broadcast(self.agent_id, content)
            await self.nc.publish("agent.broadcast", msg.encode())
        else:
            msg = MessageBuilder.send_dm(self.agent_id, to_agent, content)
            await self.nc.publish(f"agent.{to_agent}.inbox", msg.encode())

        return {"success": True, "message_id": str(msg.message_id), "to": to_agent}

    async def report_result(
        self, task_id: str, status: str, summary: str, to_agent: str = "parent"
    ) -> dict:
        if not self.nc or not self.nc.is_connected:
            return {"success": False, "error": "Not connected to NATS"}

        mt = MessageType.TASK_COMPLETE if status == "success" else MessageType.TASK_FAILED
        msg = AgentMessage(
            from_agent=self.agent_id,
            to_agent=to_agent,
            message_type=mt,
            payload={"task_id": task_id, "status": status, "summary": summary},
        )
        await self.nc.publish(f"agent.{to_agent}.inbox", msg.encode())
        return {"success": True, "task_id": task_id, "status": status}

    def get_pending_messages(self) -> list[dict]:
        messages = list(self._pending_messages)
        self._pending_messages.clear()
        return messages

    def get_known_agents(self) -> list[dict]:
        now = time.time()
        return [
            {"agent_id": aid, "role": info["role"], "age_seconds": int(now - info["last_seen"])}
            for aid, info in self._known_agents.items()
            if aid != self.agent_id
        ]


def create_mcp_server(agent_id: str, nats_url: str):
    """Create and configure the MCP server with NATS tools."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        f"tmux-mcp-{agent_id}",
        instructions=(
            "tmux workspace messaging tools for communicating with other AI agents. "
            "Use send_message to talk to other agents (like tmux send-keys), "
            "report_result to report task completion, "
            "list_agents to see who's available (like tmux list-panes), "
            "and get_messages to check incoming messages."
        ),
    )

    bridge = NATSMCPBridge(agent_id, nats_url)
    _bridge_connected = False

    async def ensure_connected():
        nonlocal _bridge_connected
        if not _bridge_connected:
            await bridge.connect()
            _bridge_connected = True

    @mcp.tool()
    async def send_message(to_agent: str, content: str) -> str:
        """Send a message to another agent.

        Args:
            to_agent: Target agent ID (e.g., "parent", "coder-1") or "broadcast" for all agents.
            content: Message content to send.

        Returns:
            JSON result with success status and message ID.
        """
        await ensure_connected()
        if to_agent == "broadcast":
            result = await bridge.send_message("", content, message_type="agent_broadcast")
        else:
            result = await bridge.send_message(to_agent, content)
        return json.dumps(result)

    @mcp.tool()
    async def report_result(
        task_id: str, status: str, summary: str, to_agent: str = "parent"
    ) -> str:
        """Report task completion or failure back to the requesting agent.

        Args:
            task_id: ID of the task being reported on.
            status: "success" or "failure".
            summary: Brief description of the result.
            to_agent: Agent to report to (default: "parent").

        Returns:
            JSON result with success status.
        """
        await ensure_connected()
        result = await bridge.report_result(task_id, status, summary, to_agent)
        return json.dumps(result)

    @mcp.tool()
    async def list_agents() -> str:
        """List currently active agents in the system.

        Returns:
            JSON array of agents with their IDs, roles, and last seen time.
        """
        await ensure_connected()
        agents = bridge.get_known_agents()
        return json.dumps(agents)

    @mcp.tool()
    async def get_messages() -> str:
        """Check for pending incoming messages.

        Returns:
            JSON array of messages received since last check.
        """
        await ensure_connected()
        messages = bridge.get_pending_messages()
        return json.dumps(messages)

    return mcp, bridge


def main():
    parser = argparse.ArgumentParser(description="tmux-mcp: MCP server for agent messaging")
    parser.add_argument("--agent-id", required=True, help="Agent identifier")
    parser.add_argument(
        "--nats-url", default=os.environ.get("NATS_URL", "nats://localhost:4222")
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format=f"%(asctime)s [tmux-mcp:{args.agent_id}] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    mcp, bridge = create_mcp_server(args.agent_id, args.nats_url)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
