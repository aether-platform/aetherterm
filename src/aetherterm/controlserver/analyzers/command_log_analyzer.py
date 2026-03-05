"""
Command log analyzer for ControlServer.

Receives terminal input/output events via NATS and maintains
a structured command log per session for audit and analysis.
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CommandRecord:
    """Single command execution record."""

    session_id: str
    agent_id: str
    command: str
    timestamp: str
    output: Optional[str] = None
    output_timestamp: Optional[str] = None


@dataclass
class SessionCommandLog:
    """Command log for a single session."""

    session_id: str
    agent_id: str
    commands: deque = field(default_factory=lambda: deque(maxlen=1000))
    total_commands: int = 0
    first_activity: Optional[str] = None
    last_activity: Optional[str] = None


class CommandLogAnalyzer:
    """Analyzes and stores command execution logs from terminal events."""

    def __init__(self, max_sessions: int = 10000):
        self._logs: Dict[str, SessionCommandLog] = {}
        self._max_sessions = max_sessions

        # Statistics
        self._total_inputs = 0
        self._total_outputs = 0

    async def handle_terminal_input(self, subject: str, data: Dict[str, Any]) -> None:
        """Handle terminal input event from NATS."""
        session_id = data.get("session_id", "")
        agent_id = data.get("agent_id", "")
        content = data.get("content", "")
        timestamp = data.get("timestamp", datetime.now().isoformat())

        if not content.strip():
            return

        self._total_inputs += 1

        log = self._get_or_create_log(session_id, agent_id)
        log.commands.append(
            CommandRecord(
                session_id=session_id,
                agent_id=agent_id,
                command=content.strip(),
                timestamp=timestamp,
            )
        )
        log.total_commands += 1
        log.last_activity = timestamp

        logger.debug(f"[{session_id}] Command logged: {content.strip()[:80]}")

    async def handle_terminal_output(self, subject: str, data: Dict[str, Any]) -> None:
        """Handle terminal output event from NATS."""
        session_id = data.get("session_id", "")
        content = data.get("content", "")
        timestamp = data.get("timestamp", datetime.now().isoformat())

        self._total_outputs += 1

        log = self._logs.get(session_id)
        if log and log.commands:
            last_cmd = log.commands[-1]
            if last_cmd.output is None:
                last_cmd.output = content[:10000]  # Cap output size
                last_cmd.output_timestamp = timestamp

    def get_session_log(self, session_id: str) -> Optional[SessionCommandLog]:
        """Get command log for a session."""
        return self._logs.get(session_id)

    def get_recent_commands(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent commands for a session."""
        log = self._logs.get(session_id)
        if not log:
            return []

        commands = list(log.commands)[-limit:]
        return [
            {
                "command": cmd.command,
                "timestamp": cmd.timestamp,
                "has_output": cmd.output is not None,
            }
            for cmd in commands
        ]

    def get_all_session_ids(self) -> List[str]:
        """Get all tracked session IDs."""
        return list(self._logs.keys())

    def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer statistics."""
        return {
            "tracked_sessions": len(self._logs),
            "total_inputs_received": self._total_inputs,
            "total_outputs_received": self._total_outputs,
            "sessions": {
                sid: {
                    "agent_id": log.agent_id,
                    "total_commands": log.total_commands,
                    "first_activity": log.first_activity,
                    "last_activity": log.last_activity,
                }
                for sid, log in self._logs.items()
            },
        }

    def _get_or_create_log(self, session_id: str, agent_id: str) -> SessionCommandLog:
        """Get or create a session command log."""
        if session_id not in self._logs:
            if len(self._logs) >= self._max_sessions:
                # Evict oldest session
                oldest = min(self._logs, key=lambda k: self._logs[k].last_activity or "")
                del self._logs[oldest]

            self._logs[session_id] = SessionCommandLog(
                session_id=session_id,
                agent_id=agent_id,
                first_activity=datetime.now().isoformat(),
            )

        return self._logs[session_id]

    def remove_session(self, session_id: str) -> None:
        """Remove session log (e.g., on session close)."""
        self._logs.pop(session_id, None)
