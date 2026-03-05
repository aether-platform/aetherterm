"""
NATS subject naming conventions for AetherTerm.

Subject hierarchy:
  aether.agent.{agent_id}.session.{event}   - session lifecycle events
  aether.agent.{agent_id}.terminal.{event}  - terminal I/O events
  aether.agent.{agent_id}.status             - agent heartbeat/status
  aether.control.command.{agent_id}          - control commands to specific agent
  aether.control.command.broadcast           - control commands to all agents
  aether.control.alert.{severity}            - security alerts from ControlServer
"""


class Subjects:
    """NATS subject builder."""

    # --- AgentServer → ControlServer (publish) ---

    @staticmethod
    def agent_session(agent_id: str, event: str) -> str:
        """Session lifecycle events: created, closed, updated."""
        return f"aether.agent.{agent_id}.session.{event}"

    @staticmethod
    def agent_terminal(agent_id: str, event: str) -> str:
        """Terminal events: input, output."""
        return f"aether.agent.{agent_id}.terminal.{event}"

    @staticmethod
    def agent_status(agent_id: str) -> str:
        """Agent heartbeat/status."""
        return f"aether.agent.{agent_id}.status"

    # --- ControlServer → AgentServer (publish) ---

    @staticmethod
    def control_command(agent_id: str) -> str:
        """Control command to a specific agent."""
        return f"aether.control.command.{agent_id}"

    @staticmethod
    def control_broadcast() -> str:
        """Control command broadcast to all agents."""
        return "aether.control.command.broadcast"

    @staticmethod
    def control_alert(severity: str) -> str:
        """Security alert from ControlServer."""
        return f"aether.control.alert.{severity}"

    # --- Subscribe patterns (wildcards) ---

    @staticmethod
    def all_agent_sessions() -> str:
        """Subscribe to all agent session events."""
        return "aether.agent.*.session.>"

    @staticmethod
    def all_agent_terminal() -> str:
        """Subscribe to all agent terminal events."""
        return "aether.agent.*.terminal.>"

    @staticmethod
    def all_agent_status() -> str:
        """Subscribe to all agent status events."""
        return "aether.agent.*.status"

    @staticmethod
    def all_control_commands() -> str:
        """Subscribe to all control commands (for a specific agent, use control_command)."""
        return "aether.control.command.>"

    @staticmethod
    def all_alerts() -> str:
        """Subscribe to all security alerts."""
        return "aether.control.alert.>"
